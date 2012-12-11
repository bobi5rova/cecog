"""
                           The CellCognition Project
        Copyright (c) 2006 - 2012 Michael Held, Christoph Sommer
                      Gerlich Lab, ETH Zurich, Switzerland
                              www.cellcognition.org

              CellCognition is distributed under the LGPL License.
                        See trunk/LICENSE.txt for details.
                 See trunk/AUTHORS.txt for author contributions.
"""

__author__ = 'Michael Held'
__date__ = '$Date$'
__revision__ = '$Rev$'
__source__ = '$URL$'

# Core module of the image processing work flow handling all positions of an
# experiment including the general setup (AnalyzerCore), and the analysis of
# a single position (PositionAnalyzer). This separation was necessary for the
# distributed computing of positions.

import os
import shutil
from collections import OrderedDict
from os.path import join, basename, isdir

from cecog import ccore
from cecog.io.imagecontainer import Coordinate
from cecog.plugin.segmentation import REGION_INFO
from cecog.analyzer import (TRACKING_DURATION_UNIT_FRAMES,
                            TRACKING_DURATION_UNIT_MINUTES,
                            TRACKING_DURATION_UNIT_SECONDS)

from cecog.analyzer.timeholder import TimeHolder
from cecog.analyzer.analyzer import CellAnalyzer
from cecog.analyzer.celltracker import ClassificationCellTracker2

from cecog.analyzer.channel import (PrimaryChannel,
                                    SecondaryChannel,
                                    TertiaryChannel)

from cecog.learning.learning import CommonClassPredictor

from cecog.traits.analyzer.featureextraction import SECTION_NAME_FEATURE_EXTRACTION
from cecog.traits.analyzer.processing import SECTION_NAME_PROCESSING
from cecog.traits.analyzer.tracking import SECTION_NAME_TRACKING

from cecog.analyzer.gallery import EventGallery
from cecog.util.logger import LoggerObject
from cecog.util.stopwatch import StopWatch
from cecog.util.util import makedirs

FEATURE_MAP = {'featurecategory_intensity': ['normbase', 'normbase2'],
               'featurecategory_haralick': ['haralick', 'haralick2'],
               'featurecategory_stat_geom': ['levelset'],
               'featurecategory_granugrey': ['granulometry'],
               'featurecategory_basicshape': ['roisize',
                                              'circularity',
                                              'irregularity',
                                              'irregularity2',
                                              'axes'],
               'featurecategory_convhull': ['convexhull'],
               'featurecategory_distance': ['distance'],
               'featurecategory_moments': ['moments']}

#XXX just use CHANNELS
CHANNEL_CLASSES = {PrimaryChannel.NAME: PrimaryChannel,
                   SecondaryChannel.NAME : SecondaryChannel,
                   TertiaryChannel.NAME : TertiaryChannel}


class PositionAnalyzer(LoggerObject):

    POSITION_LENGTH = 4
    PRIMARY_CHANNEL = PrimaryChannel.NAME
    SECONDARY_CHANNEL = SecondaryChannel.NAME
    TERTIARY_CHANNEL = TertiaryChannel.NAME

    CHANNELS = OrderedDict( primary=PrimaryChannel,
                            secondary=SecondaryChannel,
                            tertiary=TertiaryChannel)

    _info = {'stage': 0,
             'meta': 'Motif selection:',
             'text': '---',
             'min': 0,
             'max': 0,
             'progress': 0}


    def __init__(self, plate_id, P, out_dir, settings, frames,
                 lstSampleReader, dctSamplePositions, learner,
                 image_container, qthread=None, myhack=None):
        super(PositionAnalyzer, self).__init__()
        self._out_dir = out_dir
        self.settings = settings
        self._imagecontainer = image_container
        self.plate_id = plate_id
        self.origP = P
        self.P = P

        if not self.has_timelapse:
            self.settings.set('Processing', 'tracking', False)

        self._makedirs()
        self.add_file_handler(join(self._log_dir, "%s.log" %P), self._lvl.DEBUG)

        self._frames = frames # frames to process
        self.lstSampleReader = lstSampleReader
        self.dctSamplePositions = dctSamplePositions
        self.learner = learner

        self._qthread = qthread
        self._myhack = myhack

        # disable tracking
        if self.settings.get('Classification', 'collectsamples'):
            self.settings.set('Processing', 'tracking', False)
            self._frames = dctSamplePositions[self.origP]

        self.setup_classifiers()

    def setup_classifiers(self):
        self.classifier_infos = {}
        sttg = self.settings
        for channel, channel_id in self.ch_mapping.iteritems():
            self.settings.set_section('Processing')
            if sttg.get2(self._resolve_name(channel, 'classification')):
                sttg.set_section('Classification')
                classifier_infos = {'strEnvPath' :
                                        sttg.get2(self._resolve_name(channel,
                                                                     'classification_envpath')),
                                    # varnames are messed up!
                                    'strChannelId' : CHANNEL_CLASSES[channel].NAME,
                                    'channel_id': channel_id,
                                    'strRegionId' :
                                    sttg.get2(self._resolve_name(channel,
                                                                 'classification_regionname'))}
                clf = CommonClassPredictor(dctCollectSamples=classifier_infos)
                clf.importFromArff()
                clf.loadClassifier()
                classifier_infos['classifier'] = clf
                self.classifier_infos[channel] = classifier_infos

    # FIXME the following functions do moreless the same!
    def _resolve_name(self, channel, name):
        _channel_lkp = {self.PRIMARY_CHANNEL: 'primary',
                        self.SECONDARY_CHANNEL: 'secondary',
                        self.TERTIARY_CHANNEL: 'tertiary'}
        return '%s_%s' %(_channel_lkp[channel], name)

    @property
    def ch_mapping(self):
        sttg =self.settings
        chm = OrderedDict()
        chm[self.PRIMARY_CHANNEL] = sttg.get('ObjectDetection',
                                             'primary_channelid')
        if sttg.get('Processing', 'secondary_processchannel'):
            chm[self.SECONDARY_CHANNEL] = sttg.get('ObjectDetection',
                                                   'secondary_channelid')
        if sttg.get('Processing', 'tertiary_processchannel'):
            chm[self.TERTIARY_CHANNEL] = sttg.get('ObjectDetection',
                                                  'tertiary_channelid')
        return chm

    @property
    def channels_to_process(self):
        # refactor this function with ch_mapping
        channels = (PrimaryChannel.NAME, )
        for name in [SecondaryChannel.NAME, TertiaryChannel.NAME]:
            if self.settings.get('Processing', '%s_processchannel' % name.lower()):
                channels = channels + (name,)
        return channels

    @property
    def meta_data(self):
        return self._imagecontainer.get_meta_data()

    @property
    def has_timelapse(self):
        return self.meta_data.has_timelapse
        # self._has_timelapse = len(self.meta_data.times) > 1

    def _makedirs(self):
        assert isinstance(self.P, basestring)
        assert isinstance(self._out_dir, basestring)

        self._analyzed_dir = join(self._out_dir, "analyzed")
        if self.has_timelapse:
            self._position_dir = join(self._analyzed_dir, self.P)
        else:
            self._position_dir = self._analyzed_dir

        odirs = (self._analyzed_dir,
                 join(self._out_dir, "debug"),
                 join(self._out_dir, "dump"),
                 join(self._out_dir, "log"),
                 join(self._out_dir, "log", "_finished"),
                 join(self._out_dir, "hdf5"),
                 join(self._out_dir, "plots", "population"),
                 join(self._position_dir, "statistics"),
                 join(self._position_dir, "gallery"),
                 join(self._position_dir, "images"),
                 join(self._position_dir, "images","_labels"))

        for odir in odirs:
            try:
                makedirs(odir)
            except os.error: # no permissions
                self.logger.error("mkdir %s: failed" %odir)
            else:
                self.logger.info("mkdir %s: ok" %odir)
            setattr(self, "_%s_dir" %basename(odir.lower()).strip("_"), odir)

    def __del__(self):
        # XXX - is it really necessary?
        self.logger.removeHandler(self._file_handler)

    def _convert_tracking_duration(self, option_name):
        """
        Converts a tracking duration according to the unit and the
        mean time-lapse of the current position.
        Returns number of frames.
        """
        value = self.settings.get(SECTION_NAME_TRACKING, option_name)
        unit = self.settings.get(SECTION_NAME_TRACKING,
                                  'tracking_duration_unit')

        # get mean and stddev for the current position
        info = self.meta_data.get_timestamp_info(self.P)
        if unit == TRACKING_DURATION_UNIT_FRAMES or info is None:
            result = value
        elif unit == TRACKING_DURATION_UNIT_MINUTES:
            result = (value * 60.) / info[0]
        elif unit == TRACKING_DURATION_UNIT_SECONDS:
            result = value / info[0]
        else:
            raise ValueError("Wrong unit '%s' specified." % unit)
        return int(round(result))

    @property
    def _hdf_options(self):
        self.settings.set_section('Output')
        h5opts = {"hdf5_include_tracking": self.settings.get2('hdf5_include_tracking'),
                  "hdf5_include_events": self.settings.get2('hdf5_include_events'),
                  "hdf5_compression": "gzip" if self.settings.get2("hdf5_compression") else None,
                  "hdf5_create": self.settings.get2('hdf5_create_file'),
                  "hdf5_reuse": self.settings.get2('hdf5_reuse'),
                  "hdf5_include_raw_images": self.settings.get2('hdf5_include_raw_images'),
                  "hdf5_include_label_images": self.settings.get2('hdf5_include_label_images'),
                  "hdf5_include_features": self.settings.get2('hdf5_include_features'),
                  "hdf5_include_crack": self.settings.get2('hdf5_include_crack'),
                  "hdf5_include_classification": self.settings.get2('hdf5_include_classification')}

        # Processing overwrites Output
        if not self.settings.get('Processing', 'tracking'):
            h5opts["hdf5_include_tracking"] = False
            h5opts["hdf5_include_events"] = False
        return h5opts

    @property
    def _tracking_options(self):
        tropts = {'fMaxObjectDistance': self.settings.get2('tracking_maxobjectdistance'),
                  'iMaxSplitObjects': self.settings.get2('tracking_maxsplitobjects'),
                  'iMaxTrackingGap': self.settings.get2('tracking_maxtrackinggap'),
                  'bExportTrackFeatures': self.settings.get2('tracking_exporttrackfeatures'),
                  'featureCompression': None if self.settings.get2('tracking_compressiontrackfeatures') == 'raw' else self.settings.get2('tracking_compressiontrackfeatures'),
                  'bHasClassificationData': True,
                  'iBackwardCheck': 0,
                  'iForwardCheck': 0,
                  'iBackwardRange': -1,
                  'iForwardRange': -1,
                  'iMaxInDegree': self.settings.get2('tracking_maxindegree'),
                  'iMaxOutDegree': self.settings.get2('tracking_maxoutdegree'),
                  'lstLabelTransitions': [],
                  'lstBackwardLabels': [],
                  'lstForwardLabels': []}

        # if event selection is on
        # what is this good for?
        transitions = self.settings.get2('tracking_labeltransitions').replace('),(', ')__(')
        transitions = map(eval, transitions.split('__'))
        if self.settings.get('Processing', 'tracking_synchronize_trajectories'):
            tropts.update({'iBackwardCheck': self._convert_tracking_duration('tracking_backwardCheck'),
                           'iForwardCheck': self._convert_tracking_duration('tracking_forwardCheck'),
                           'iBackwardRange': self._convert_tracking_duration('tracking_backwardrange'),
                           'iForwardRange': self._convert_tracking_duration('tracking_forwardrange'),
                           'bBackwardRangeMin': self.settings.get2('tracking_backwardrange_min'),
                           'bForwardRangeMin': self.settings.get2('tracking_forwardrange_min'),
                           'lstLabelTransitions': transitions,
                           'lstBackwardLabels': map(int, self.settings.get2('tracking_backwardlabels').split(',')),
                           'lstForwardLabels': map(int, self.settings.get2('tracking_forwardlabels').split(','))})
        return tropts

    def define_exp_features(self):
        features = {}
        for name in [PrimaryChannel.NAME, SecondaryChannel.NAME,
                     TertiaryChannel.NAME]:
            region_features = {}
            for region in REGION_INFO.names[name.lower()]:
                # export all features extracted per regions
                if self.settings.get('Output', 'events_export_all_features') or \
                        self.settings.get('Output', 'export_track_data'):
                    region_features[region] = None
                # export selected features from settings
                else:
                    region_features[region] = \
                        self.settings.get('General',
                                          '%s_featureextraction_exportfeaturenames'
                                          % name.lower())
            features[name] = region_features
        return features

    def export_object_counts(self, timeholder):
        fname = join(self._statistics_dir, 'P%s__object_counts.txt' % self.P)

        # at least the total count for primary is always exported
        ch_info = {'Primary': ('primary', [], [])}

        for ch_name, channel_id in self.ch_mapping.iteritems():
            if self.classifier_infos.has_key(ch_name):
                infos = self.classifier_infos[ch_name]
                ch_info[ch_name] = (infos['strRegionId'],
                                    infos['classifier'].lstClassNames,
                                    infos['classifier'].lstHexColors)

        timeholder.exportObjectCounts(fname, self.P, self.meta_data, ch_info)
        pplot_ymax = \
            self.settings.get('Output', 'export_object_counts_ylim_max')

        # plot only for primary channel so far!
        timeholder.exportPopulationPlots(fname, self._population_dir, self.P,
                                         self.meta_data, ch_info['Primary'], pplot_ymax)


    def export_object_details(self, timeholder):
        fname = join(self._statistics_dir,
                        'P%s__object_details.txt' % self.P)
        timeholder.exportObjectDetails(fname, excel_style=False)
        fname = join(self._statistics_dir,
                        'P%s__object_details_excel.txt' % self.P)
        timeholder.exportObjectDetails(fname, excel_style=True)

    def export_image_names(self, timeholder):
        timeholder.exportImageFileNames(self._statistics_dir,
                                         self.P,
                                         self._imagecontainer,
                                         self.ch_mapping)

    def export_full_tracks(self, celltracker):
        celltracker.exportFullTracks()

    def export_graphviz(self, celltracker):
        self.oCellTracker.exportGraph(\
            join(self._statistics_dir, 'tracking_graph___P%s.dot' % self.P))

    def export_gallery_images(self, celltracker):
        gallery_images = ['primary']
        for prefix in [SecondaryChannel.PREFIX, TertiaryChannel.PREFIX]:
            if self.settings.get('Processing', '%s_processchannel' % prefix):
                gallery_images.append(prefix)

        for render_name in gallery_images:
            cutter_in = join(self._images_dir, render_name)
            if isdir(cutter_in):
                cutter_out = join(self._gallery_dir, render_name)
                self.logger.info("running Cutter for '%s'..." % render_name)
                image_size = \
                    self.settings.get('Output', 'events_gallery_image_size')
                EventGallery(celltracker, cutter_in, self.P, cutter_out,
                             self.meta_data, oneFilePerTrack=True,
                             size=(image_size, image_size))
            # FIXME: be careful here. normally only raw images are
            #        used for the cutter and can be deleted
            #        afterwards
            shutil.rmtree(cutter_in, ignore_errors=True)

    def tracking(self, timeholder, celltracker):
        """Invoke Tracking, just tracking"""
        self.logger.debug("--- serializing tracking start")
        timeholder.serialize_tracking(celltracker)
        self.logger.debug("--- serializing tracking ok")

        if self.is_aborted():
            return 0 # number of processed images
        self.update_stage({'text': "find events"})

        self.logger.debug("--- visitor start")
        celltracker.initVisitor()
        self.logger.debug("--- visitor ok")

    def event_selection(self, timeholder, celltracker):
        """Invoke event_selection"""
        celltracker.analyze(self.export_features,
                            channelId=PrimaryChannel.NAME,
                            clear_path=True)

        self.logger.debug("--- visitor analysis ok")
        timeholder.serialize_events(celltracker)
        self.logger.debug("--- serializing events ok")

    def __call__(self):
        self.logger.info('')
        # turn libtiff warnings off
        if not __debug__:
            ccore.turn_off()
        stopwatch = StopWatch(start=True)
        self.settings.set_section('Output')

        # include hdf5 file name in hdf5_options
        # perhaps timeholder might be a good placke to read out the options
        # fils must not exist to proceed
        hdf5_fname = join(self._hdf5_dir, '%s.hdf5' % self.P)
        self.oTimeHolder = TimeHolder(self.P, self.channels_to_process,
                                      hdf5_fname,
                                      self.meta_data, self.settings,
                                      self._frames,
                                      self.plate_id,
                                      **self._hdf_options)

        self.settings.set_section('Tracking')
        # structure and logic to handle object trajectories
        if not self.settings.get('Processing', 'tracking'):
            self.oCellTracker = None
        else:
            clsCellTracker = ClassificationCellTracker2
            self.oCellTracker = clsCellTracker(oTimeHolder=self.oTimeHolder,
                                               oMetaData=self.meta_data,
                                               P=self.P,
                                               origP=self.origP,
                                               strPathOut=self._statistics_dir,
                                               **self._tracking_options)
            primary_channel_id = PrimaryChannel.NAME
            region_name = self.settings.get2('tracking_regionname')
            self.oCellTracker.initTrackingAtTimepoint(primary_channel_id, region_name)


        # object detection??
        ca = CellAnalyzer(time_holder=self.oTimeHolder,
                          position = self.P,
                          create_images = True,
                          binning_factor = 1,
                          detect_objects = self.settings.get('Processing', 'objectdetection'))

        self.export_features = self.define_exp_features()
        n_images = self._analyzePosition(ca)

        if n_images > 0:
            # exports also
            if self.settings.get('Output', 'export_object_counts'):
                self.export_object_counts(self.oTimeHolder)
            if self.settings.get('Output', 'export_object_details'):
                self.export_object_details(self.oTimeHolder)
            if self.settings.get('Output', 'export_file_names'):
                self.export_image_names(self.oTimeHolder)

            # invoke tracking
            self.settings.set_section('Tracking')
            if self.settings.get('Processing', 'tracking'):
                ret = self.tracking(self.oTimeHolder, self.oCellTracker)
                if self.is_aborted() or ret == 0:
                    return 0 # number of processed images
                self.update_stage({'text': 'export events...'})
                # invoke event selection
                if self.settings.get('Processing', 'tracking_synchronize_trajectories'):
                    self.event_selection(self.oTimeHolder, self.oCellTracker)

                if self.settings.get('Output', 'export_track_data'):
                    self.export_full_tracks(self.oCellTracker)
                if self.settings.get('Output', 'export_tracking_as_dot'):
                    self.export_graphviz(self.oCellTracker)

            if self.is_aborted():
                return 0
            self.update_stage({'text': 'export events...',
                               'max': 1,
                               'progress': 1})

            # remove all features from all channels to free memory
            # for the generation of gallery images
            self.oTimeHolder.purge_features()
            if self.settings.get('Output', 'events_export_gallery_images'):
                self.export_gallery_images(self.oCellTracker)

        try:
            intval = stopwatch.stop()/n_images*1000
        except ZeroDivisionError:
            pass
        else:
            self.logger.info(" - %d image sets analyzed, %3d ms per image set" %
                             (n_images, intval))

        self.touch_finished()
        self.clear()
        return {'iNumberImages': n_images, 'filename_hdf5': hdf5_fname}

    def touch_finished(self, times=None):
        """Writes an empty file to mark this position as finished"""
        fname = join(self._finished_dir, '%s__finished.txt' % self.P)
        with open(fname, "w") as f:
            os.utime(fname, times)

    def clear(self):
        # closes hdf5
        self.oTimeHolder.close_all()

    def is_aborted(self):
        if self._qthread is None:
            return False
        elif self._qthread.get_abort():
            return True

    def update_stage(self, info):
        self._info.update(info)
        if not self._qthread is None:
            self._qthread.set_stage_info(self._info, stime=0.1)

    def registration_shift(self):
        # FIXME this function causses a segfault on c++ side in compination
        # with cropping
        # compute values for the registration of multiple channels
        # (translation only)
        self.settings.set_section('ObjectDetection')
        xs = [0]
        ys = [0]
        for prefix in [SecondaryChannel.PREFIX, TertiaryChannel.PREFIX]:
            if self.settings.get('Processing','%s_processchannel' % prefix):
                reg_x = self.settings.get2('%s_channelregistration_x' % prefix)
                reg_y = self.settings.get2('%s_channelregistration_y' % prefix)
                xs.append(reg_x)
                ys.append(reg_y)
        diff_x = []
        diff_y = []
        for i in range(len(xs)):
            for j in range(i, len(xs)):
                diff_x.append(abs(xs[i]-xs[j]))
                diff_y.append(abs(ys[i]-ys[j]))

        # new image size after registration of all images
        image_size = (self.meta_data.dim_x - max(diff_x),
                      self.meta_data.dim_y - max(diff_y))
#
        self.meta_data.real_image_width = image_size[0]
        self.meta_data.real_image_height = image_size[1]

        # relative start point of registered image
        return (max(xs), max(ys)), image_size

    def zslice_par(self, ch_name):
        """Returns either the number of the zslice to select or a tuple of parmeters
        to control the zslice projcetion"""
        self.settings.set_section('ObjectDetection')
        if self.settings.get2(self._resolve_name(ch_name, 'zslice_selection')):
            par = self.settings.get2(self._resolve_name(
                    ch_name, 'zslice_selection_slice'))
        elif self.settings.get2(self._resolve_name(ch_name, 'zslice_projection')):
            method = self.settings.get2(self._resolve_name(
                    ch_name, 'zslice_projection_method'))
            begin = self.settings.get2(self._resolve_name(
                    ch_name, 'zslice_projection_begin'))
            end = self.settings.get2(self._resolve_name(
                    ch_name, 'zslice_projection_end'))
            step = self.settings.get2(self._resolve_name(
                    ch_name, 'zslice_projection_step'))
            par = (method, begin, end, step)
        return par

    def feature_params(self, ch_name):

        # XXX unify list and dict
        f_categories = list()
        f_cat_params = dict()

        # unfortunateley some classes expecte empty list and dict
        if not self.settings.get(SECTION_NAME_PROCESSING,
                             self._resolve_name(ch_name,
                                                'featureextraction')):
            return f_categories, f_cat_params

        for category, feature in FEATURE_MAP.iteritems():
            if self.settings.get(SECTION_NAME_FEATURE_EXTRACTION,
                                 self._resolve_name(ch_name, category)):
                if "haralick" in category:
                    try:
                        f_cat_params['haralick_categories'].extend(feature)
                    except KeyError:
                        assert isinstance(feature, list)
                        f_cat_params['haralick_categories'] = feature
                else:
                    f_categories += feature

        if f_cat_params.has_key("haralick_categories"):
            f_cat_params['haralick_distances'] = (1, 2, 4, 8)

        return f_categories, f_cat_params

    def setup_channel(self, ch_name, channel_id):
        prefix = ch_name.lower()

        # determine the list of features to be calculated from each object
        f_cats, f_params = self.feature_params(ch_name)
        reg_shift, im_size = self.registration_shift()
        ch_cls = self.CHANNELS[prefix]

        if ch_name == self.PRIMARY_CHANNEL:
            channel_registration = (0,0)
        elif ch_name in [self.SECONDARY_CHANNEL, self.TERTIARY_CHANNEL]:
            channel_registration = (self.settings.get2('%s_channelregistration_x' % prefix),
                                    self.settings.get2('%s_channelregistration_y' % prefix))

        channel = ch_cls(strChannelId=channel_id,
                         oZSliceOrProjection = self.zslice_par(ch_name),
                         channelRegistration = channel_registration,
                         new_image_size = im_size,
                         registration_start = reg_shift,
                         fNormalizeMin = self.settings.get2('%s_normalizemin' % prefix),
                         fNormalizeMax = self.settings.get2('%s_normalizemax' % prefix),
                         lstFeatureCategories = f_cats,
                         dctFeatureParameters = f_params)
        return channel

    def _analyzePosition(self, cellanalyzer):

        self._info.update({'stage': 2,
                           'min': 1,
                           'max': len(self._frames),
                           'meta' : 'Image processing:',
                           'item_name': 'image set'})

        n_images = 0
        last_frame = self._frames[-1]
        stopwatch = StopWatch(start=True)

        # here self.P is also as good
        crd = Coordinate(self.plate_id, self.origP,
                         self._frames, list(set(self.ch_mapping.values())))
        for frame, iter_channel in self._imagecontainer(crd,
                                                        interrupt_channel=True,
                                                        interrupt_zslice=True):

            if self.is_aborted():
                self.clear()
                return 0
            else:
                txt = 'T %d (%d/%d)' %(frame, self._frames.index(frame)+1,
                                       len(self._frames))
                self.update_stage({'progress': self._frames.index(frame)+1,
                                   'text': txt,
                                   'interval': stopwatch.interim()})
            stopwatch.reset(start=True)
            cellanalyzer.initTimepoint(frame)

            # loop over the channels
            for channel_id, iter_zslice in iter_channel:
                zslice_images = [meta_image for _, meta_image in iter_zslice]
                for ch_name in self.channels_to_process:
                    # each process channel has a destinct color channel
                    if channel_id != self.ch_mapping[ch_name]:
                        continue

                    channel = self.setup_channel(ch_name, channel_id)
                    # loop over the z-slices
                    for meta_image in zslice_images:
                        channel.append_zslice(meta_image)
                    cellanalyzer.register_channel(channel)

            # PICKING
            if self.settings.get('Classification', 'collectsamples'):
                img_rgb = cellanalyzer.collectObjects(self.plate_id,
                                                      self.origP,
                                                      self.lstSampleReader,
                                                      self.learner,
                                                      byTime=True)
                if not img_rgb is None:
                    n_images += 1
                    if not self._qthread is None:
                        #if self._qthread.get_renderer() == strType:
                        self._qthread.set_image(None,
                                                img_rgb,
                                                'PL %s - P %s - T %05d' % (self.plate_id, self.origP, frame))
            #END PICKING
            else:
                cellanalyzer.process()
                n_images += 1
                # if not self._qthread:
                #     time.sleep(.1)

                images = []
                if self.settings.get('Processing', 'tracking'):
                    self.oCellTracker.trackAtTimepoint(frame)

                    self.settings.set_section('Tracking')
                    if self.settings.get2('tracking_visualization'):
                        size = cellanalyzer.getImageSize(PrimaryChannel.NAME)
                        img_conn, img_split = self.oCellTracker.visualizeTracks(frame, size,
                                                                                n=self.settings.get2('tracking_visualize_track_length'),
                                                                                radius=self.settings.get2('tracking_centroid_radius'))
                        images += [(img_conn, '#FFFF00', 1.0),
                                   (img_split, '#00FFFF', 1.0)]

                for name, infos in self.classifier_infos.iteritems():
                    cellanalyzer.classify_objects(infos['classifier'])

                ##############################################################
                # FIXME - part for browser
                if not self._myhack is None:
                    self.render_browser(cellanalyzer)
                ##############################################################

                self.settings.set_section('General')
                self.render_classification_images(cellanalyzer, images, frame)
                self.render_contour_images(cellanalyzer, images, frame)

                if self.settings.get('Output', 'rendering_labels_discwrite'):
                    cellanalyzer.exportLabelImages(self._labels_dir)

            self.logger.info(" - Frame %d, duration (ms): %3d" \
                                 %(frame, stopwatch.interim()*1000))
            cellanalyzer.purge(features=self.export_features)

        return n_images

    def render_contour_images(self, cellanalyzer, images, frame):
        for region, render_info in self.settings.get2('rendering').iteritems():
            out_images = join(self._images_dir, region)
            write = self.settings.get('Output', 'rendering_contours_discwrite')
            img_rgb, filename = cellanalyzer.render(out_images,
                                                    dctRenderInfo=render_info,
                                                    writeToDisc=write,
                                                    images=images)

            if (not self._qthread is None and not img_rgb is None):
                msg = 'PL %s - P %s - T %05d' % (self.plate_id, self.origP, frame)
                self._qthread.set_image(region, img_rgb, msg, filename, stime=0.05)

    def render_classification_images(self, cellanalyzer, images, frame):
        for region, render_info in self.settings.get2('rendering_class').iteritems():
            out_images = join(self._images_dir, region)
            write = self.settings.get('Output', 'rendering_class_discwrite')
            img_rgb, filename = cellanalyzer.render(out_images,
                                                    dctRenderInfo=render_info,
                                                    writeToDisc=write,
                                                    images=images)

            # emit image to gui
            if not self._qthread is None and not img_rgb is None:
                msg = 'PL %s - P %s - T %05d' % (self.plate_id, self.origP, frame)
                self._qthread.set_image(region, img_rgb, msg, filename, stime=0.05)

    def render_browser(self, cellanalyzer):
        d = {}
        for name in cellanalyzer.get_channel_names():
            channel = cellanalyzer.get_channel(name)
            d[channel.strChannelId] = channel.meta_image.image
            self._myhack.set_image(d)

        channel_name, region_name = self._myhack._object_region
        channel = cellanalyzer.get_channel(channel_name)
        if channel.has_region(region_name):
            region = channel.get_region(region_name)
            coords = {}
            for obj_id, obj in region.iteritems():
                coords[obj_id] = obj.crack_contour
            self._myhack.set_coords(coords)
