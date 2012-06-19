"""
                           The CellCognition Project
                     Copyright (c) 2006 - 2010 Michael Held
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

#-------------------------------------------------------------------------------
# standard library imports:
#

import os, \
       types, \
       logging, \
       zlib, \
       base64

#-------------------------------------------------------------------------------
# extension module imports:
#
from pdk.propertymanagers import PropertyManager
from pdk.properties import (BooleanProperty,
                            IntProperty,
                            StringProperty,
                            InstanceProperty,
                            )
from pdk.attributes import Attribute
from pdk.map import dict_append_list
from pdk.fileutils import safe_mkdirs
from pdk.iterator import flatten
from pdk.ordereddict import OrderedDict

import numpy
import h5py

#-------------------------------------------------------------------------------
# cecog module imports:
#

from cecog import ccore

from cecog.util.util import hexToRgb
from cecog.analyzer import REGION_NAMES_SECONDARY
from cecog.io.imagecontainer import Coordinate
from cecog.analyzer.channel import PrimaryChannel

#-------------------------------------------------------------------------------
# constants:
#

#-------------------------------------------------------------------------------
# functions:
#

#-------------------------------------------------------------------------------
# classes:
#

class TimeHolder(OrderedDict):

    HDF5_GRP_DEFINITION = "definition"
    HDF5_GRP_RELATION = "relation"
    HDF5_GRP_IMAGE = "image"
    HDF5_GRP_TIME = "time"
    HDF5_GRP_ZSLICE = "zslice"
    HDF5_GRP_OBJECT = "object"
    HDF5_GRP_FEATURE = "feature"
    HDF5_GRP_FEATURE_SET = "feature_set"
    HDF5_GRP_CLASSIFICATION = "classification"
    HDF5_GRP_ANNOTATION = "annotation"
    HDF5_GRP_CLASSIFIER = "classifier"
    HDF5_GRP_REGION = "region"
    HDF5_NAME_ID = "id"
    HDF5_NAME_EDGE = "edge"
    HDF5_ATTR_DESCRIPTION = "description"
    HDF5_OTYPE_REGION = 'region'
    HDF5_OTYPE_OBJECT = 'object'

    HDF5_DTYPE_RELATION = \
         numpy.dtype([('obj_idx1', 'uint32'),
                      ('obj_idx2', 'uint32'),])

    HDF5_DTYPE_TERMINAL_RELATION = \
         numpy.dtype([('obj_id1', 'uint32'),
                      ('obj_idx1', 'uint32', 2),
                      ('obj_id2', 'uint32'),
                      ('obj_idx2', 'uint32', 2),])

    HDF5_DTYPE_EDGE = \
        numpy.dtype([('obj_id', 'uint32'),
                     ('relation_idx', 'uint32'),])

    HDF5_DTYPE_ID = \
        numpy.dtype([('obj_id', 'uint32'),
                     ('edge_idx1', 'uint32'),
                     ('edge_idx2', 'uint32'),])


    def __init__(self, P, channels, filename_hdf5, meta_data, settings,
                 analysis_frames, plate_id,
                 hdf5_create=True, hdf5_compression='gzip',
                 hdf5_include_raw_images=True,
                 hdf5_include_label_images=True, hdf5_include_features=True,
                 hdf5_include_classification=True, hdf5_include_crack=True,
                 hdf5_include_tracking=True, hdf5_include_events=True, hdf5_include_annotation=True):
        super(TimeHolder, self).__init__()
        self.P = P
        self.plate_id = plate_id
        self._iCurrentT = None
        self.channels = channels
        self._meta_data = meta_data
        self._settings = settings
        self._analysis_frames = analysis_frames

        self._hdf5_create = hdf5_create
        self._hdf5_include_raw_images = hdf5_include_raw_images
        self._hdf5_include_label_images = hdf5_include_label_images
        self._hdf5_include_features = hdf5_include_features
        self._hdf5_include_classification = hdf5_include_classification
        self._hdf5_include_crack = hdf5_include_crack
        self._hdf5_include_tracking = hdf5_include_tracking
        self._hdf5_include_events = hdf5_include_events
        self._hdf5_include_annotation = hdf5_include_annotation
        self._hdf5_compression = hdf5_compression

        self._hdf5_features_complete = False
        self.hdf5_filename = filename_hdf5

        self._logger = logging.getLogger(self.__class__.__name__)
        # frames get an index representation with the NC file, starting at 0
        frames = sorted(analysis_frames)
        self._frames_to_idx = dict([(f,i) for i, f in enumerate(frames)])
        self._idx_to_frames = dict([(i,f) for i, f in enumerate(frames)])
        self._object_coord_to_id = {}
        self._object_coord_to_idx = {}

        self._channel_info = [('primary',
                               settings.get('ObjectDetection',
                                            'primary_channelid'))]
        self._region_infos = [('primary',
                               self._convert_region_name('primary','primary'),
                               'primary')]
        settings.set_section('ObjectDetection')
        for prefix in ['secondary', 'tertiary']:
            if settings.get('Processing', '%s_processchannel' % prefix):
                name = settings.get('ObjectDetection', '%s_channelid' % prefix)
                self._channel_info.append((prefix, name))
                for name in REGION_NAMES_SECONDARY:
                    if settings.get2('%s_regions_%s' % (prefix, name)):
                        self._region_infos.append((prefix,
                                                   self._convert_region_name(prefix, name),
                                                   name))

        self._channels_to_idx = OrderedDict([(n[0], i) for i, n in
                                             enumerate(self._channel_info)])
        self._regions_to_idx = OrderedDict([(n[1], i) for i, n in
                                            enumerate(self._region_infos)])
        self._edge_to_idx = {}

        self._classifier_to_idx = {}

        self._feature_to_idx = OrderedDict()

        if self._hdf5_create:
            self._hdf5_create_file_structure()
            self._hdf5_write_global_definition()
            
    def _hdf5_write_global_definition(self):
        """
        """
        
        ### global channel description
        dtype = numpy.dtype([('channel_name', '|S50'),
                             ('description', '|S100'),
                             ('is_physical', bool),
                             ('voxel_size', 'float', 3),
                             ])

        nr_channels = len(self._channel_info)
        global_channel_desc = self._grp_def[self.HDF5_GRP_IMAGE].create_dataset('channel', (nr_channels,), dtype)
        for idx in self._channels_to_idx.values():
            data = (self._channel_info[idx][0],
                    self._channel_info[idx][1],
                    True,
                    (0, 0, 0))
            global_channel_desc[idx] = data
            
        ### global region description
        dtype = numpy.dtype([('region_name', '|S50'), ('channel_idx', 'i')])
        nr_labels = len(self._regions_to_idx)
        global_region_desc = self._grp_def[self.HDF5_GRP_IMAGE].create_dataset(self.HDF5_GRP_REGION, (nr_labels,), dtype)
        for tpl in self._region_infos:
            channel_name, combined = tpl[:2]
            idx = self._regions_to_idx[combined]
            channel_idx = self._channels_to_idx[channel_name]
            global_region_desc[idx] = (combined, channel_idx)

#        # number of region (terminal objects)
#        nr_objects = len(self._regions_to_idx)
#        
#        # plus number of relation object mappings
#        
#        nr_objects += (nr_objects - 1)
#        if self._hdf5_include_tracking:
#            nr_objects += 1
#        if self._hdf5_include_events:
#            nr_objects += 1

        ### global object definition
            
        # add the basic regions
        global_object_dtype = numpy.dtype([('name', '|S512'), ('type', '|S512'), ('source1', '|S512'), ('source2', '|S512')])
        
        for channel_name, combined, region_name in self._region_infos: 
            obj_name = self._convert_region_name(channel_name, region_name, prefix='')
            global_object_desc = self._grp_def[self.HDF5_GRP_OBJECT].create_dataset(obj_name, (1,), global_object_dtype)
            global_object_desc[0] = (obj_name, self.HDF5_OTYPE_REGION, '', '')

        # add basic relation objects (primary -> secondary etc)
        prim_obj_name = self._convert_region_name(self._region_infos[0][0], self._region_infos[0][2], prefix='')
        for channel_name, combined, region_name in self._region_infos[1:]:
            # relation between objects from different regions
            # (in cecog 1:1 from primary only)
            if channel_name != PrimaryChannel.PREFIX:
                obj_name = self._convert_region_name(channel_name, region_name, prefix='')
                obj_name = '%s___to___%s' % (prim_obj_name, obj_name)
                global_object_desc = self._grp_def[self.HDF5_GRP_OBJECT].create_dataset(obj_name, (1,), global_object_dtype)
                global_object_desc[0] =  (obj_name, self.HDF5_OTYPE_OBJECT,
                                          prim_obj_name,
                                          obj_name)
 
        # add special relation objects (events, tracking, etc)
        if self._hdf5_include_tracking:
            obj_name = 'tracking'
            global_object_desc = self._grp_def[self.HDF5_GRP_OBJECT].create_dataset(obj_name, (1,), global_object_dtype)
            global_object_desc[0] = (obj_name, self.HDF5_OTYPE_REGION, prim_obj_name, prim_obj_name)
            
        if self._hdf5_include_events:
            obj_name = 'event'
            global_object_desc = self._grp_def[self.HDF5_GRP_OBJECT].create_dataset(obj_name, (1,), global_object_dtype)
            global_object_desc[0] = (obj_name, self.HDF5_OTYPE_REGION, prim_obj_name, prim_obj_name)

                       
    def _hdf5_create_file_structure(self):
        f = h5py.File(self.hdf5_filename, 'w')
        self._hdf5_file = f

        grp_sample = f.create_group('sample')
        grp_cur_sample = grp_sample.create_group('0')
        grp_plate = grp_cur_sample.create_group('plate')
        grp_cur_plate = grp_plate.create_group(self.plate_id)
        
        meta_data = self._meta_data

        # Check for being wellbased or old style (B01_03 vs. 0037)
        if meta_data.has_well_info:
            well, subwell = meta_data.get_well_and_subwell(self.P)
            position = str(subwell)
        else:
            well = "0"
            position = self.P
        grp_experiment = grp_cur_plate.create_group('experiment')
        grp_cur_experiment = grp_experiment.create_group(well)
        grp_position = grp_cur_experiment.create_group('position')
        grp_cur_position = grp_position.create_group(position)

        self._grp_cur_position = grp_cur_position
        
        self._grp_cur_position.create_group(self.HDF5_GRP_IMAGE)
        self._grp_cur_position.create_group(self.HDF5_GRP_FEATURE)
        self._grp_cur_position.create_group(self.HDF5_GRP_OBJECT)

        self._grp_def = f.create_group(self.HDF5_GRP_DEFINITION)
        
        self._grp_def.create_group(self.HDF5_GRP_IMAGE)
        self._grp_def.create_group(self.HDF5_GRP_FEATURE)
        self._grp_def.create_group(self.HDF5_GRP_OBJECT)

        
    
    def _hdf5_write_image(self):
        pass

    @staticmethod
    def nc_valid_set(var, idx, value):
        helper = var.valid
        if len(helper.shape) == 0:
            helper = value
        else:
            helper[idx] = value
        var.valid = helper

    def close_all(self):
        if self._hdf5_create:
            self._hdf5_file.close()

    def initTimePoint(self, iT):
        # HDF5 feature definition is complete after first frame
        if not self._iCurrentT is None:
            self._hdf5_features_complete = True
        self._iCurrentT = iT

    def getCurrentTimePoint(self):
        return self._iCurrentT

    def getCurrentChannels(self):
        return self[self._iCurrentT]
    
    def purge_features(self):
        for channels in self.itervalues():
            for channel in channels.itervalues():
                channel.purge(features={})

    def _convert_region_name(self, channel_name, region_name, prefix='region'):
        s = '%s__%s' % (channel_name.lower(), region_name)
        if not prefix is None and len(prefix) > 0:
            s = '%s___%s' % (prefix, s)
        return s

    def _convert_feature_name(self, feature_name, channel_name, region_name):
        return '__'.join([feature_name, channel_name, region_name])
    
    def apply_channel(self, oChannel):
        iT = self._iCurrentT
        if not iT in self:
            self[iT] = OrderedDict()
        self[iT][oChannel.NAME] = oChannel
        self[iT].sort(key = lambda x: self[iT][x])

    def apply_segmentation(self, channel, primary_channel=None):
        desc = '[P %s, T %05d, C %s]' % (self.P, self._iCurrentT,
                                         channel.strChannelId)
        name = channel.NAME.lower()
        if False:#self._create_nc or self._reuse_nc:
            grp = self._dataset.groups[self.NC_GROUP_LABEL]
            grp = grp.groups[name]
            frame_idx = self._frames_to_idx[self._iCurrentT]
        if False:#self._reuse_nc:
            for region_name in channel.lstAreaSelection:
                var = grp.variables[region_name]
                if len(var.valid.shape) == 0:
                    frame_valid = var.valid
                else:
                    frame_valid = var.valid[frame_idx]
                if frame_valid:
                    img_label = ccore.numpy_to_image(var[frame_idx],
                                                     copy=True)
                    img_xy = channel.meta_image.image
                    container = ccore.ImageMaskContainer(img_xy, img_label,
                                                         False, True, True)
                    channel.dctContainers[region_name] = container
                    valid = True
                else:
                    valid = False
                    break

        channel.apply_segmentation(primary_channel)

        if self._hdf5_create and self._hdf5_include_label_images:
            meta = self._meta_data
            w = meta.real_image_width
            h = meta.real_image_height
            z = meta.dim_z
            t = len(self._frames_to_idx)
            var_name = 'region'
            grp = self._grp_cur_position[self.HDF5_GRP_IMAGE]
            if var_name in grp:
                var_labels = grp[var_name]
            else:
                nr_labels = len(self._regions_to_idx)
                var_labels = \
                    grp.create_dataset(var_name,
                                       (nr_labels, t, z, h, w),
                                       'uint16',
                                       chunks=(1, 5, 1, h/5, w/5),
                                       compression=self._hdf5_compression)

            frame_idx = self._frames_to_idx[self._iCurrentT]
            for region_name in channel.lstAreaSelection:
                idx = self._regions_to_idx[
                        self._convert_region_name(channel.PREFIX, region_name)]
                container = channel.dctContainers[region_name]
                array = container.img_labels.toArray(copy=False)
                var_labels[idx, frame_idx, 0] = numpy.require(array, 'uint16')


    def prepare_raw_image(self, channel):
        desc = '[P %s, T %05d, C %s]' % (self.P, self._iCurrentT,
                                         channel.strChannelId)
        if False:#self._create_nc or self._reuse_nc:
            grp = self._dataset.groups[self.NC_GROUP_RAW]
            var = grp.variables[channel.strChannelId]
            frame_idx = self._frames_to_idx[self._iCurrentT]
            
            if len(var.valid.shape) == 0:
                frame_valid = var.valid
            else:
                frame_valid = var.valid[frame_idx]
                    
        if False:#self._reuse_nc and frame_valid:
            coordinate = Coordinate(position=self.P, time=self._iCurrentT,
                                    channel=channel.strChannelId, zslice=1)
            meta_image = MetaImage(image_container=None, coordinate=coordinate)

            img = ccore.numpy_to_image(var[frame_idx], copy=True)
            meta_image.set_image(img)
            meta_image.set_raw_image(img)
            channel.meta_image = meta_image
            self._logger.debug('Raw image %s loaded from nc4 file.' % desc)
        else:
            channel.apply_zselection()
            channel.normalize_image()
            channel.apply_registration()
            if False:#self._create_nc:
                img = channel.meta_image.image
                grp = self._dataset.groups[self.NC_GROUP_RAW]
                var = grp.variables[channel.strChannelId]
                var[frame_idx] = img.toArray(copy=False)
                self.nc_valid_set(var, frame_idx, 1)
                self._logger.debug('Raw image %s written to nc4 file.' % desc)

        
        channel.apply_zselection()
        channel.normalize_image()
        channel.apply_registration()

        if self._hdf5_create and self._hdf5_include_raw_images:
            meta = self._meta_data
            w = meta.real_image_width
            h = meta.real_image_height
            z = meta.dim_z
            t = len(self._frames_to_idx)
            nr_channels = len(self._channel_info)
            var_name = 'channel'
            grp = self._grp_cur_position[self.HDF5_GRP_IMAGE]
            if var_name in grp:
                var_images = grp[var_name]
            else:
                var_images = \
                    grp.create_dataset(var_name,
                                       (nr_channels, t, z, h, w),
                                       'uint8',
                                       chunks=None,
                                       compression=self._hdf5_compression)

            frame_idx = self._frames_to_idx[self._iCurrentT]
            channel_idx = self._channels_to_idx[channel.PREFIX]
            img = channel.meta_image.image
            array = img.toArray(copy=False)
            var_images[channel_idx, frame_idx, 0] = array

    def _get_feature_group(self):
        grp_object_features = self._grp_cur_position.require_group(self.HDF5_GRP_FEATURE)
        return grp_object_features

    def apply_features(self, channel):
        channel_name = channel.NAME.lower()
        channel.apply_features()

        if self._hdf5_create:
            grp_cur_pos = self._grp_cur_position
            grp_feature = self._get_feature_group()
            for region_name in channel.region_names():
                combined_region_name = self._convert_region_name(channel_name, region_name, '')

                region = channel.get_region(region_name)
                feature_names = region.getFeatureNames()
                nr_features = len(feature_names)
                nr_objects = len(region)
                
                grp_region_features = grp_feature.require_group(combined_region_name)
                
                # create object mapping tables
                if combined_region_name not in grp_cur_pos[self.HDF5_GRP_OBJECT]:
                    dtype = numpy.dtype([('time_idx', 'int32'),
                                         ('obj_label_id', 'int32'),
                                         ])
    
                    dset_idx_relation = grp_cur_pos[self.HDF5_GRP_OBJECT].create_dataset(combined_region_name,
                                                          (nr_objects,),
                                                          dtype,
                                                          chunks=(nr_objects,),
                                                          compression=self._hdf5_compression,
                                                          maxshape=(None,))
                    offset = 0
                else:
                    dset_idx_relation = grp_cur_pos[self.HDF5_GRP_OBJECT][combined_region_name]
                    offset = len(dset_idx_relation)
                    dset_idx_relation.resize((nr_objects + offset,))
                
                # Create dataset for bounding box
                if 'bounding_box' not in grp_region_features:
                    dtype = numpy.dtype([('left', 'int32'),
                                         ('right', 'int32'),
                                         ('top', 'int32'),
                                         ('bottom', 'int32'),
                                         ])
                    
                    dset_bounding_box = grp_region_features.create_dataset('bounding_box',
                                                          (nr_objects,),
                                                          dtype,
                                                          chunks=(nr_objects,),
                                                          compression=self._hdf5_compression,
                                                          maxshape=(None,))
                else:
                    dset_bounding_box = grp_region_features['bounding_box']
                    dset_bounding_box.resize((nr_objects + offset,))
                
                # Create dataset for center
                if 'center' not in grp_region_features:
                    dtype = numpy.dtype([('x', 'int32'),
                                         ('y', 'int32'),])
                    
                    dset_center = grp_region_features.create_dataset('center',
                                                          (nr_objects,),
                                                          dtype,
                                                          chunks=(nr_objects,),
                                                          compression=self._hdf5_compression,
                                                          maxshape=(None,))
                else:
                    dset_center = grp_region_features['center']
                    dset_center.resize((nr_objects + offset,))

                if (self._hdf5_include_features or self._hdf5_include_classification):
                    # Create dataset for center
                    if 'object_features' not in grp_region_features:
                        dset_object_features = grp_region_features.create_dataset('object_features',
                                                          (nr_objects, nr_features),
                                                          dtype='float',
                                                          compression=self._hdf5_compression,
                                                          maxshape=(None, nr_features))
                    else:
                        dset_object_features = grp_region_features['object_features']
                        dset_object_features.resize((nr_objects + offset, nr_features))
                    
                if self._hdf5_include_crack:
                    if 'crack_contour' not in grp_region_features:
                        dt = h5py.new_vlen(str)
                        dset_crack_contour = grp_region_features.create_dataset('crack_contour',
                                                (nr_objects, ), dt,
                                                chunks=(nr_objects, ),
                                                compression=self._hdf5_compression,
                                                maxshape=(None,))
                    else:
                        dset_crack_contour = grp_region_features['crack_contour']
                        dset_crack_contour.resize((nr_objects + offset, ))
                    
                    
                frame_idx = self._frames_to_idx[self._iCurrentT]       
                for idx, obj_id in enumerate(region):
                    obj = region[obj_id]

                    dset_bounding_box[idx + offset] = obj.oRoi.upperLeft[0], obj.oRoi.lowerRight[0], obj.oRoi.upperLeft[1], obj.oRoi.lowerRight[1]
                    dset_center[idx + offset] = obj.oCenterAbs

                    dset_idx_relation[idx + offset] = frame_idx, obj_id

                    if self._hdf5_include_features:
                        dset_object_features[idx + offset] = obj.aFeatures

                    if self._hdf5_include_crack:
                        data = ','.join(map(str, flatten(obj.crack_contour)))
                        dset_crack_contour[idx + offset] = base64.b64encode(zlib.compress(data))
                

    def serialize_tracking(self, tracker):
        graph = tracker.get_graph()
        
        # export full graph structure to .dot file
        #path_out = self._settings.get('General', 'pathout')
        #tracker.exportGraph(os.path.join(path_out, 'graph.dot'))
        if self._hdf5_create and self._hdf5_include_tracking:
            grp = self._grp_cur_position[self.HDF5_GRP_OBJECT]

            head_nodes = [node_id for node_id in graph.node_list()
                          if graph.in_degree(node_id) == 0 and graph.out_degree(node_id) > 0]
            nr_edges = graph.number_of_edges()
            nr_objects = len(head_nodes)

            # export graph structure of every head node to .dot file
            #for node_id in head_nodes:
            #    tracker.exportSubGraph(os.path.join(path_out, 'graph__%s.dot' % node_id), node_id)

            var_rel = grp.create_dataset('tracking',
                                         (nr_edges, ),
                                         self.HDF5_DTYPE_RELATION,
                                         chunks=(nr_edges,),
                                         compression=self._hdf5_compression)
#            grp = self._grp_cur_position[self.HDF5_GRP_OBJECT]
#            grp_cur_obj = grp.create_group('track')
#            var_id = grp_cur_obj.create_dataset(self.HDF5_NAME_ID, (nr_objects,), self.HDF5_DTYPE_ID)

            prefix = PrimaryChannel.PREFIX
            data = []
            for idx, edge in enumerate(graph.edges.itervalues()):
                head_id, tail_id = edge[:2]
                head_frame, head_obj_id = \
                    tracker.getComponentsFromNodeId(head_id)[:2]
                head_frame_idx = self._frames_to_idx[head_frame]
                tail_frame, tail_obj_id = \
                    tracker.getComponentsFromNodeId(tail_id)[:2]
                tail_frame_idx = self._frames_to_idx[tail_frame]

                #head_obj_id_meta = self._object_coord_to_id[(prefix, (head_frame_idx, head_obj_id))]
                head_obj_idx_meta = self._object_coord_to_idx[(prefix, (head_frame_idx, head_obj_id))]
                #tail_obj_id_meta = self._object_coord_to_id[(prefix, (tail_frame_idx, tail_obj_id))]
                tail_obj_idx_meta = self._object_coord_to_idx[(prefix, (tail_frame_idx, tail_obj_id))]

                data.append((head_obj_idx_meta,
                             tail_obj_idx_meta))
                self._edge_to_idx[(head_id, tail_id)] = idx
                
            var_rel[:] = data
            # traverse the graph structure by head nodes and save one object per head node
            # (with all forward-reachable nodes)
#            data = []
#            for obj_idx, head_id in enumerate(head_nodes):
#                obj_id = obj_idx + 1
#                edge_idx_start = len(data)
#                edge_list = graph.dfs_edges(head_id)
#                
#                for head, tail in edge_list:
#                    rel_idx = self._edge_to_idx[(head, tail)]
#                    data.append((obj_id, rel_idx))
#                
#                var_id[obj_idx] = (obj_id, edge_idx_start, len(data))
#
#            var_edge = grp_cur_obj.create_dataset(self.HDF5_NAME_EDGE, (len(data),), 
#                                                  self.HDF5_DTYPE_EDGE)
#            var_edge[:] = data

    def serialize_events(self, tracker):
        if False:#self._hdf5_create and self._hdf5_include_events:
            event_lookup = {}
            for events in tracker.dctVisitorData.itervalues():
                for start_id, event in events.iteritems():
                    if start_id[0] != '_':
                        key = tracker.getComponentsFromNodeId(start_id)[:2]
                        event_lookup.setdefault(key, []).append(event) 
            nr_events = len(event_lookup)
            nr_edges = 0
            for events in event_lookup.itervalues():
                if len(events) == 1:
                    nr_edges += events[0]['maxLength'] - 1
                elif len(events) == 2:
                    splt = events[0]['splitIdx']
                    nr_edges += events[0]['maxLength'] + events[1]['maxLength'] - splt - 1
                else:
                    raise ValueError("More than two daughter cell are not supported.")

            grp = self._grp_cur_position[self.HDF5_GRP_OBJECT]
            grp_cur_obj = grp.create_group('event')
            
            if nr_events > 0:
                var_edge = grp_cur_obj.create_dataset(self.HDF5_NAME_EDGE, (nr_edges,), self.HDF5_DTYPE_EDGE, maxshape=(None,))
                var_id = grp_cur_obj.create_dataset(self.HDF5_NAME_ID, (nr_events,), self.HDF5_DTYPE_ID, maxshape=(None,))
                
                obj_idx = 0
                rel_idx = 0
                for events in event_lookup.itervalues():
                    obj_id = obj_idx + 1
                    rel_idx_start = rel_idx
                    track = events[0]['tracks'][0]
                    for head_id, tail_id in zip(track, track[1:]):
                        edge_idx = self._edge_to_idx[(head_id, tail_id)]
                        var_edge[rel_idx] = (obj_id, edge_idx)
                        rel_idx += 1
                    if len(events) == 2:
                        splt = events[1]['splitIdx']
                        track = events[1]['tracks'][0][splt-1:]
                        for head_id, tail_id in zip(track, track[1:]):
                            edge_idx = self._edge_to_idx[(head_id, tail_id)]
                            var_edge[rel_idx] = (obj_id, edge_idx)
                            rel_idx += 1
                        
                    var_id[obj_idx] = (obj_id, rel_idx_start, rel_idx)
                    obj_idx += 1
            else:
                var_edge = grp_cur_obj.create_dataset(self.HDF5_NAME_EDGE, (0,), 
                                                      self.HDF5_DTYPE_EDGE, 
                                                      chunks=(1,), maxshape=(None,))
                var_id = grp_cur_obj.create_dataset(self.HDF5_NAME_ID, (0,), 
                                                    self.HDF5_DTYPE_ID, 
                                                    chunks=(1,), maxshape=(None,))
                   
    def serialize_annotation(self, channel_name, region_name, annotation):
        if False:#self._hdf5_create and self._hdf5_include_annotation:
            channel = self[self._iCurrentT][channel_name]
            region = channel.get_region(region_name)
            combined_region_name = \
                self._convert_region_name(channel_name, region_name, prefix=None)
                
            var_name = self.HDF5_GRP_ANNOTATION
                
            if not var_name in self._grp_def:
                dt = numpy.dtype([('name', '|S512'),
                                  ('user', '|S512'),
                                  ('date_str', '|S16'),
                                  ('object', '|S512'),
                                  ('classification', '|S512'),
                                  ('description', '|S512')])
                var = self._grp_def.create_dataset(var_name, (1,), dt,
                                                   chunks=(1,),
                                                   compression=self._hdf5_compression,
                                                   maxshape=(None,))
                offset = 0
            else:
                var = self._grp_def[var_name]
                offset = var.shape[0]
                var.resize((offset+1,))
            
            var[offset] = (annotation.name, annotation.user, annotation.date_str, 
                           combined_region_name, annotation.classification_schema,
                           annotation.description)
            
            # TODO: fisish this by implementing a annotation object which is generated by
            # the browser and can be reused here...

    def serialize_classification(self, channel_name, region_name, predictor):
        if self._hdf5_create and self._hdf5_include_classification:
            channel = self[self._iCurrentT][channel_name]
            region = channel.get_region(region_name)
            combined_region_name = self._convert_region_name(channel_name, region_name, prefix=None)
            
            nr_classes = predictor.iClassNumber
            nr_objects = len(region)
            
            ### 1) write global classifier definition
            
            global_def_group = self._grp_def[self.HDF5_GRP_FEATURE].require_group(combined_region_name)
            
            classification_group = global_def_group.require_group('object_classification')
            
            # class labels
            if 'class_labels' not in classification_group:
                dt = numpy.dtype([('label', 'int32'),
                                  ('name', '|S100'),
                                  ('color', '|S9')])
                var = classification_group.create_dataset('class_labels', (nr_classes,), dt)
                var[:] = zip(predictor.lstClassLabels, predictor.lstClassNames, predictor.lstHexColors)
                
                # classifier
                dt = numpy.dtype([('name', '|S512'),
                                          ('method', '|S512'),
                                          ('version', '|S512'),
                                          ('parameter', '|S512'),
                                          ('description', '|S512')])
                var = classification_group.create_dataset('classifier', (1,), dt)
                
                var[0] = (predictor.name,
                                   predictor.oClassifier.METHOD,
                                   predictor.oClassifier.NAME,
                                   '',
                                   '')
                
                feature_names = predictor.lstFeatureNames
                var = classification_group.create_dataset('features', (len(feature_names),), [('object_feautres','|S512'),])
                var[:] = feature_names
            
            ### 2) write prediction and probablilities
            current_classification_grp = self._grp_cur_position.require_group('object_classification')
            
            if 'prediction' not in current_classification_grp:
                dt = numpy.dtype([('label_idx', 'int32')])
                dset_prediction = current_classification_grp.create_dataset('prediction', 
                                                                            (nr_objects, ), dt,
                                                                            chunks=(nr_objects,),
                                                                            compression=self._hdf5_compression,
                                                                            maxshape=(None,))
                offset = 0 
            else:
                dset_prediction = current_classification_grp['prediction']
                offset = len(dset_prediction)
                dset_prediction.resize((nr_objects + offset,))
                
            var_name = 'probability'
            if not var_name in current_classification_grp:
                dset_pobability = current_classification_grp.create_dataset(var_name, (nr_objects, nr_classes),
                                           'float',
                                           chunks=(nr_objects, nr_classes),
                                           compression=self._hdf5_compression,
                                           maxshape=(None, nr_classes)
                                           )
                offset = 0
            else:
                dset_pobability = current_classification_grp[var_name]
                offset = len(dset_pobability)
                dset_pobability.resize((offset+nr_objects, nr_classes))

            label_to_idx = dict([(label, i)
                                 for i, label in
                                 enumerate(predictor.lstClassLabels)])
            
            for obj_idx, obj_id in enumerate(region):
                obj = region[obj_id]
                dset_prediction[obj_idx + offset] = (label_to_idx[obj.iLabel],)
                dset_pobability[obj_idx + offset] = obj.dctProb.values()

    def extportObjectCounts(self, filename, P, meta_data, prim_info=None,
                            sec_info=None, sep='\t'):
        f = file(filename, 'w')
        has_header = False

        for frame, channels in self.iteritems():
            #channels.sort(key = lambda x: channels[x])

            line1 = []
            line2 = []
            line3 = []
            line4 = []
            items = []
            coordinate = Coordinate(position=P, time=frame)
            prefix = [frame, meta_data.get_timestamp_relative(coordinate)]
            prefix_names = ['frame', 'time']

            for channel in channels.values():
                if channel.NAME == 'Primary' and not prim_info is None:
                    region_info = prim_info
                elif channel.NAME == 'Secondary' and not sec_info is None:
                    region_info = sec_info
                else:
                    region_info = None

                if not region_info is None:
                    region_name, class_names = region_info
                    if not has_header:
                        keys = ['total'] + class_names
                        line4 += keys
                        line3 += ['total'] + ['class']*len(class_names)
                        line1 += [channel.NAME.upper()] * len(keys)
                        line2 += [region_name] * len(keys)

                    if channel.has_region(region_name):
                        region = channel.get_region(region_name)
                        total = len(region)
                        count = dict([(x, 0) for x in class_names])
                        # in case just total counts are needed
                        if len(class_names) > 0:
                            for obj in region.values():
                                count[obj.strClassName] += 1
                        items += [total] + [count[x] for x in class_names]
                    else:
                        items += [numpy.NAN] * (len(class_names) + 1)

            if not has_header:
                has_header = True
                prefix_str = [''] * len(prefix)
                f.write('%s\n' % sep.join(prefix_str + line1))
                f.write('%s\n' % sep.join(prefix_str + line2))
                f.write('%s\n' % sep.join(prefix_str + line3))
                f.write('%s\n' % sep.join(prefix_names + line4))

            f.write('%s\n' % sep.join(map(str, prefix + items)))

        f.close()


    def extportObjectDetails(self, filename, sep='\t', excel_style=False):
        f = file(filename, 'w')

        feature_lookup = OrderedDict()
        feature_lookup['mean'] = 'n2_avg'
        feature_lookup['sd'] = 'n2_stddev'
        feature_lookup['size'] = 'roisize'

        has_header = False
        line1 = []
        line2 = []
        line3 = []

        for frame, channels in self.iteritems():

            items = []
            prim_region = channels.values()[0].get_region('primary')

            for obj_id in prim_region:

                prefix = [frame, obj_id]
                prefix_names = ['frame', 'objID']
                items = []

                for channel in channels.values():

                    for region_id in channel.region_names():

                        region = channel.get_region(region_id)
                        if obj_id in region:
                            #FIXME:
                            feature_lookup2 = feature_lookup.copy()
                            for k,v in feature_lookup2.items():
                                if not region.hasFeatureName(v):
                                    del feature_lookup2[k]

                            if not has_header:
                                keys = ['classLabel', 'className']
                                if channel.NAME == 'Primary':
                                    keys += ['centerX', 'centerY']
                                keys += feature_lookup2.keys()
                                if excel_style:
                                    line1 += [channel.NAME.upper()] * len(keys)
                                    line2 += [region_id] * len(keys)
                                    line3 += keys
                                else:
                                    line1 += ['%s_%s_%s' % (channel.NAME.upper(),
                                                            region_id, key)
                                              for key in keys]

                            obj = region[obj_id]
                            #print feature_lookup2.keys(), feature_lookup2.values()
                            #fn = region.getFeatureNames()
                            #print zip(fn, obj.aFeatures)
                            features = region.getFeaturesByNames(obj_id, feature_lookup2.values())
                            values = [x if not x is None else '' for x in [obj.iLabel, obj.strClassName]]
                            if channel.NAME == 'Primary':
                                values += [obj.oCenterAbs[0], obj.oCenterAbs[1]]
                            values += list(features)
                            items.extend(values)

                if not has_header:
                    has_header = True
                    prefix_str = [''] * len(prefix)
                    if excel_style:
                        line1 = prefix_str + line1
                        line2 = prefix_str + line2
                        line3 = prefix_names + line3
                        f.write('%s\n' % sep.join(line1))
                        f.write('%s\n' % sep.join(line2))
                        f.write('%s\n' % sep.join(line3))
                    else:
                        line1 = prefix_names + line1
                        f.write('%s\n' % sep.join(line1))

                f.write('%s\n' % sep.join(map(str, prefix + items)))
        f.close()
        
    def extportImageFileNames(self, output_path, position_str, imagecontainer, channel_mapping):
        channel_mapping_reversed = dict([(v,k) for k,v in channel_mapping.iteritems()])
        filename = os.path.join(output_path, 'P%s__image_files.txt' % self.P)
        importer = imagecontainer._importer
        table = {}
        for c in channel_mapping:
            table[c] = []
        for t in self.keys():
            for c in channel_mapping.values():
                for z in importer.dimension_lookup[position_str][t][c]:
                    c_name = channel_mapping_reversed[c]
                    table[c_name].append(os.path.join(importer.path, importer.dimension_lookup[position_str][t][c][z]))
                    
        f = open(filename, 'w')
        f.write("\t".join(table.keys()) + "\n")
        for image_file_names in zip(*table.values()):
            f.write("\t".join(image_file_names) + "\n")
        f.close()
            
        


class CellAnalyzer(PropertyManager):

    PROPERTIES = \
        dict(P =
                 StringProperty(True, doc=''),
             bCreateImages =
                 BooleanProperty(True, doc="Create output images"),
             iBinningFactor =
                 IntProperty(None,
                             is_mandatory=True,
                             doc=''),
             detect_objects =
                 BooleanProperty(True),


             time_holder =
                 InstanceProperty(None,
                                  TimeHolder,
                                  doc="Instance of TimeHolder.",
                                  is_mandatory=True),
            )

    __attributes__ = [Attribute('_channel_registry'),
                      Attribute('_iT'),
                      Attribute('_oLogger'),
                      ]

    def __init__(self, **dctOptions):
        super(CellAnalyzer, self).__init__(**dctOptions)
        self._oLogger = logging.getLogger(self.__class__.__name__)

    def initTimepoint(self, iT):
        self._channel_registry = OrderedDict()
        self._iT = iT
        self.time_holder.initTimePoint(iT)

    def register_channel(self, channel):
        self._channel_registry[channel.NAME] = channel

    def get_channel_names(self):
        return self._channel_registry.keys()

    def get_channel(self, name):
        return self._channel_registry[name]

    def process(self, apply=True, extract_features=True):
        # sort by Channel `RANK`
        channels = sorted(self._channel_registry.values())
        primary_channel = None
        
        
        
        for channel in channels:

            self.time_holder.prepare_raw_image(channel)

            if self.detect_objects:
                self.time_holder.apply_segmentation(channel, primary_channel)
                if extract_features:
                    self.time_holder.apply_features(channel)

                if primary_channel is None:
                    assert channel.RANK == 1
                    primary_channel = channel

        if apply:
            for channel in channels:
                self.time_holder.apply_channel(channel)
                
    def purge(self, features=None):
        for oChannel in self._channel_registry.values():
            if not features is None and oChannel.strChannelId in features:
                channelFeatures = features[oChannel.strChannelId]
            else:
                channelFeatures = None
            oChannel.purge(features=channelFeatures)

    def exportLabelImages(self, pathOut, compression='LZW'):
        for name, channel in self._channel_registry.iteritems():
            channel_id = channel.strChannelId
            for strRegion, oContainer in channel.dctContainers.iteritems():
                strPathOutImage = os.path.join(pathOut,
                                               channel_id,
                                               strRegion)
                safe_mkdirs(strPathOutImage)
                oContainer.exportLabelImage(os.path.join(strPathOutImage,
                                                         'P%s_T%05d.tif' % (self.P, self._iT)),
                                            compression)

    def getImageSize(self, name):
        oChannel = self._channel_registry[name]
        w = oChannel.meta_image.width
        h = oChannel.meta_image.height
        return (w,h)

    def render(self, strPathOut, dctRenderInfo=None,
               strFileSuffix='.jpg', strCompression='98', writeToDisc=True,
               images=None):
        lstImages = []
        if not images is None:
            lstImages += images

        if dctRenderInfo is None:
            for name, oChannel in self._channel_registry.iteritems():
                for strRegion, oContainer in oChannel.dctContainers.iteritems():
                    strHexColor, fAlpha = oChannel.dctAreaRendering[strRegion]
                    imgRaw = oChannel.meta_image.image
                    imgCon = ccore.Image(imgRaw.width, imgRaw.height)
                    ccore.drawContour(oContainer.getBinary(), imgCon, 255, False)
                    lstImages.append((imgRaw, strHexColor, 1.0))
                    lstImages.append((imgCon, strHexColor, fAlpha))
        else:
            for channel_name, dctChannelInfo in dctRenderInfo.iteritems():
                if channel_name in self._channel_registry:
                    oChannel = self._channel_registry[channel_name]
                    if 'raw' in dctChannelInfo:
                        strHexColor, fAlpha = dctChannelInfo['raw']
                        ### Flip this and use drawContours with fill option enables to get black background 
#                        imgRaw = oChannel.meta_image.image
#                        imgCon = ccore.Image(imgRaw.width, imgRaw.height)
#                        imgCon.init(0)
#                        lstImages.append((imgCon, strHexColor, 1.0))
                        lstImages.append((oChannel.meta_image.image, strHexColor, 1.0))

                    if 'contours' in dctChannelInfo:
                        # transform the old dict-style to the new tuple-style,
                        # which allows multiple definitions for one region
                        if type(dctChannelInfo['contours']) == types.DictType:
                            lstContourInfos = [(k,)+v
                                               for k,v in dctChannelInfo['contours'].iteritems()]
                        else:
                            lstContourInfos = dctChannelInfo['contours']

                        for tplData in lstContourInfos:
                            strRegion, strNameOrColor, fAlpha, bShowLabels = tplData[:4]

                            # draw contours only if region is present
                            if oChannel.has_region(strRegion):
                                if len(tplData) > 4:
                                    bThickContours = tplData[4]
                                else:
                                    bThickContours = False
                                if strNameOrColor == 'class_label':
                                    oContainer = oChannel.dctContainers[strRegion]
                                    oRegion = oChannel.get_region(strRegion)
                                    dctLabels = {}
                                    dctColors = {}
                                    for iObjId, oObj in oRegion.iteritems():
                                        iLabel = oObj.iLabel
                                        if not iLabel is None:
                                            if not iLabel in dctLabels:
                                                dctLabels[iLabel] = []
                                            dctLabels[iLabel].append(iObjId)
                                            dctColors[iLabel] = oObj.strHexColor
                                    #print dctLabels
                                    imgRaw = oChannel.meta_image.image
                                    imgCon2 = ccore.Image(imgRaw.width, imgRaw.height)
                                    for iLabel, lstObjIds in dctLabels.iteritems():
                                        imgCon = ccore.Image(imgRaw.width, imgRaw.height)
                                         ### Flip this and use drawContours with fill option enables to get black background 
                                        oContainer.drawContoursByIds(lstObjIds, 255, imgCon, bThickContours, False)
#                                        oContainer.drawContoursByIds(lstObjIds, 255, imgCon, bThickContours, True)
                                        lstImages.append((imgCon, dctColors[iLabel], fAlpha))

                                        if type(bShowLabels) == types.BooleanType and bShowLabels:
                                        #    oContainer.drawTextsByIds(lstObjIds, lstObjIds, imgCon2)
                                        #else:
                                            oContainer.drawTextsByIds(lstObjIds, [str(iLabel)]*len(lstObjIds), imgCon2)
                                    lstImages.append((imgCon2, '#FFFFFF', 1.0))

                                else:
                                    oContainer = oChannel.dctContainers[strRegion]
                                    oRegion = oChannel.get_region(strRegion)
                                    lstObjIds = oRegion.keys()
                                    imgRaw = oChannel.meta_image.image
                                    imgCon = ccore.Image(imgRaw.width, imgRaw.height)
                                    if not strNameOrColor is None:
                                        oContainer.drawContoursByIds(lstObjIds, 255, imgCon, bThickContours, False)
                                    else:
                                        strNameOrColor = '#FFFFFF'
                                    lstImages.append((imgCon, strNameOrColor, fAlpha))
                                    if bShowLabels:
                                        imgCon2 = ccore.Image(imgRaw.width, imgRaw.height)
                                        oContainer.drawLabelsByIds(lstObjIds, imgCon2)
                                        lstImages.append((imgCon2, '#FFFFFF', 1.0))


        if len(lstImages) > 0:
            imgRgb = ccore.makeRGBImage([x[0].getView() for x in lstImages],
                                        [ccore.RGBValue(*hexToRgb(x[1])) for x in lstImages],
                                        [x[2] for x in lstImages])

            if writeToDisc:
                strFilePath = os.path.join(strPathOut, "P%s_T%05d%s" % (self.P, self._iT, strFileSuffix))
                safe_mkdirs(strPathOut)
                ccore.writeImage(imgRgb, strFilePath, strCompression)
                self._oLogger.debug("* rendered image written '%s'" % strFilePath)
            else:
                strFilePath = ''
            return imgRgb, strFilePath


    def collectObjects(self, plate_id, P, lstReader, oLearner, byTime=True):

        #channel_name = oLearner.strChannelId
        strRegionId = oLearner.strRegionId
        img_rgb = None

        self._oLogger.debug('* collecting samples...')

#        bSuccess = True
#        channels = sorted(self._channel_registry.values())
#        primary_cChannel = None
#        for channel2 in lstChannels:
#
#            self.time_holder.prepare_raw_image(channel)
#            self.time_holder.apply_segmentation(oChannel2, oPrimaryChannel)
#
#            if oPrimaryChannel is None:
#                assert oChannel2.RANK == 1
#                oPrimaryChannel = oChannel2
        self.process(apply = False, extract_features = False)

        # self._channel_registry
        oChannel = self._channel_registry[oLearner.channel_name]
        oContainer = oChannel.get_container(strRegionId)
        objects = oContainer.getObjects()

        object_lookup = {}
        for oReader in lstReader:
            lstCoordinates = None
            if (byTime and P == oReader.getPosition() and self._iT in oReader):
                lstCoordinates = oReader[self._iT]
            elif (not byTime and P in oReader):
                lstCoordinates = oReader[P]
            #print "moo", P, oReader.getPosition(), byTime, self._iT in oReader
            #print lstCoordinates, byTime, self.P, oReader.keys()

            if not lstCoordinates is None:
                #print self.iP, self._iT, lstCoordinates
                for dctData in lstCoordinates:
                    label = dctData['iClassLabel']
                    if (label in oLearner.dctClassNames and
                        dctData['iPosX'] >= 0 and
                        dctData['iPosX'] < oContainer.width and
                        dctData['iPosY'] >= 0 and
                        dctData['iPosY'] < oContainer.height):

                        center1 = ccore.Diff2D(dctData['iPosX'],
                                               dctData['iPosY'])

                        # test for obj_id "under" annotated pixel first
                        obj_id = oContainer.img_labels[center1]

                        # if not background: valid obj_id found
                        if obj_id > 0:
                            dict_append_list(object_lookup, label, obj_id)

                        # otherwise try to find nearest object in a search
                        # radius of 30 pixel (compatibility with CellCounter)
                        else:
                            dists = []
                            for obj_id, obj in objects.iteritems():
                                diff = obj.oCenterAbs - center1
                                dist_sq = diff.squaredMagnitude()
                                # limit to 30 pixel radius
                                if dist_sq < 900:
                                    dists.append((obj_id, dist_sq))
                            if len(dists) > 0:
                                dists.sort(lambda a,b: cmp(a[1], b[1]))
                                obj_id = dists[0][0]
                                dict_append_list(object_lookup, label, obj_id)

        object_ids = set(flatten(object_lookup.values()))
        objects_del = set(objects.keys()) - object_ids
        for obj_id in objects_del:
            oContainer.delObject(obj_id)

        self.time_holder.apply_features(oChannel)
        region = oChannel.get_region(strRegionId)

        learner_objects = []
        for label, object_ids in object_lookup.iteritems():
            class_name = oLearner.dctClassNames[label]
            hex_color = oLearner.dctHexColors[class_name]
            rgb_value = ccore.RGBValue(*hexToRgb(hex_color))
            for obj_id in object_ids:
                obj = region[obj_id]
                obj.iLabel = label
                obj.strClassName = class_name
                obj.strHexColor = hex_color

                if (obj.oRoi.upperLeft[0] >= 0 and
                    obj.oRoi.upperLeft[1] >= 0 and
                    obj.oRoi.lowerRight[0] < oContainer.width and
                    obj.oRoi.lowerRight[1] < oContainer.height):
                    iCenterX, iCenterY = obj.oCenterAbs

                    strPathOutLabel = os.path.join(oLearner.dctEnvPaths['samples'],
                                                   oLearner.dctClassNames[label])
                    safe_mkdirs(strPathOutLabel)

                    strFilenameBase = 'PL%s___P%s___T%05d___X%04d___Y%04d' % (plate_id, self.P, self._iT, iCenterX, iCenterY)

                    obj.sample_id = strFilenameBase
                    learner_objects.append(obj)

                    strFilenameImg = os.path.join(strPathOutLabel, '%s___img.png' % strFilenameBase)
                    strFilenameMsk = os.path.join(strPathOutLabel, '%s___msk.png' % strFilenameBase)
                    # FIXME: export Objects is segfaulting for objects
                    #        where its bounding box is touching the border
                    #        i.e. one corner point equals zero!
                    oContainer.exportObject(obj_id,
                                            strFilenameImg,
                                            strFilenameMsk)

                    oContainer.markObjects([obj_id], rgb_value, False, True)

                    #print obj_id, obj.oCenterAbs, iCenterX, iCenterY
                    print '*** CSdebug: drawFilledCircle', iCenterX, iCenterY
                    ccore.drawFilledCircle(ccore.Diff2D(iCenterX, iCenterY),
                                           3, oContainer.img_rgb, rgb_value)


        if len(learner_objects) > 0:
            oLearner.applyObjects(learner_objects)
            # we don't want to apply None for feature names
            oLearner.setFeatureNames(oChannel.lstFeatureNames)

        strPathOut = os.path.join(oLearner.dctEnvPaths['controls'])
        safe_mkdirs(strPathOut)
        oContainer.exportRGB(os.path.join(strPathOut,
                                          "P%s_T%05d_C%s_R%s.jpg" %\
                                           (self.P, self._iT, oLearner.strChannelId, oLearner.strRegionId)),
                            '90')
        img_rgb = oContainer.img_rgb
        return img_rgb


    def classify_objects(self, predictor):
        channel_name = predictor.strChannelId
        region_name = predictor.strRegionId
        channel = self._channel_registry[channel_name]
        region = channel.get_region(region_name)
        for obj in region.itervalues():
            label, probs = predictor.predict(obj.aFeatures,
                                             region.getFeatureNames())
            obj.iLabel = label
            obj.dctProb = probs
            obj.strClassName = predictor.dctClassNames[label]
            obj.strHexColor = predictor.dctHexColors[obj.strClassName]

        self.time_holder.serialize_classification(channel_name, region_name,
                                                  predictor)
        
        
        
####### Old style of writing time-lapse information  
#        if self._meta_data.has_timelapse:
#            dtype = numpy.dtype([('frame', 'i'), ('timestamp_abs', 'i'),
#                                 ('timestamp_rel', 'i')])
#            nr_frames = len(frames)
#            var = grp_def_pos.create_dataset(self.HDF5_GRP_TIME,
#                                        (nr_frames,), dtype,
#                                        chunks=(nr_frames,),
#                                        compression=self._hdf5_compression)
#            for frame in frames:
#                idx = self._frames_to_idx[frame]
#                coord = Coordinate(position=self.P, time=frame)
#                ts_abs = meta_data.get_timestamp_absolute(coord)
#                ts_rel = meta_data.get_timestamp_relative(coord)
#                var[idx] = (frame, ts_abs, ts_rel)
