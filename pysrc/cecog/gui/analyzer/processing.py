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

__all__ = ['ProcessingFrame']

#-------------------------------------------------------------------------------
# standard library imports:
#

#-------------------------------------------------------------------------------
# extension module imports:
#

#-------------------------------------------------------------------------------
# cecog imports:
#
from cecog.traits.analyzer.processing import SECTION_NAME_PROCESSING
from cecog.gui.analyzer import (BaseProcessorFrame,
                                AnalzyerThread,
                                HmmThread,
                                )
from cecog.analyzer.channel import (PrimaryChannel,
                                    SecondaryChannel,
                                    TertiaryChannel,
                                    )
from cecog.plugin.segmentation import REGION_INFO

#-------------------------------------------------------------------------------
# constants:
#


#-------------------------------------------------------------------------------
# functions:
#


#-------------------------------------------------------------------------------
# classes:
#
class ProcessingFrame(BaseProcessorFrame):

    SECTION_NAME = SECTION_NAME_PROCESSING

    def __init__(self, settings, parent):
        super(ProcessingFrame, self).__init__(settings, parent)

        self.register_control_button('process',
                                     [AnalzyerThread,
                                      HmmThread],
                                     ('Start processing', 'Stop processing'))

        self.add_group(None,
                       [('primary_featureextraction', (0,0,1,1)),
                        ('primary_classification', (1,0,1,1)),
                        ('tracking', (2,0,1,1)),
                        ('tracking_synchronize_trajectories', (3,0,1,1)),
                        ('primary_errorcorrection', (4,0,1,1))
                        ], link='primary_channel', label='Primary channel')

        for prefix in ['secondary', 'tertiary']:
            self.add_group('%s_processchannel' % prefix,
                           [('%s_featureextraction' % prefix, (0,0,1,1)),
                            ('%s_classification' % prefix, (1,0,1,1)),
                            ('%s_errorcorrection' % prefix, (2,0,1,1))
                            ])

        #self.add_line()

        self.add_expanding_spacer()

        self._init_control()

    @classmethod
    def get_special_settings(cls, settings, has_timelapse=True):
        settings = BaseProcessorFrame.get_special_settings(settings, has_timelapse)

        settings.set('General', 'rendering', {})
        settings.set('General', 'rendering_class', {})

        additional_prefixes = [SecondaryChannel.PREFIX, TertiaryChannel.PREFIX]
        settings.set_section('Classification')
        sec_class_regions = dict([(prefix,
                                  settings.get2('%s_classification_regionname' % prefix))
                                  for prefix in additional_prefixes])

        settings.set_section('ObjectDetection')

#        lookup = dict([(v,k) for k,v in SECONDARY_REGIONS.iteritems()])
#        # FIXME: we should rather show a warning here!
#        if not sec_region in sec_regions:
#            sec_regions.append(sec_region)
#            settings.set2(lookup[sec_region], True)

        show_ids = settings.get('Output', 'rendering_contours_showids')
        show_ids_class = settings.get('Output', 'rendering_class_showids')

        colors = REGION_INFO.colors
        for prefix in ['primary', 'secondary', 'tertiary']:
            if prefix == 'primary' or settings.get('Processing', '%s_processchannel' % prefix):
                d = dict([('%s_contours_%s' % (prefix, x),
                                               {prefix.capitalize(): {'raw': ('#FFFFFF', 1.0),
                                                                      'contours': [(x, colors[x], 1, show_ids)]
                                               }})
                                               for x in REGION_INFO.names[prefix]])
                settings.get('General', 'rendering').update(d)

                if settings.get('Processing', '%s_classification' % prefix):
                    d = dict([('%s_classification_%s' % (prefix, x),
                                                   {prefix.capitalize(): {'raw': ('#FFFFFF', 1.0),
                                                                          'contours': [(x, 'class_label', 1, False),
                                                                                       (x, '#000000' , 1, show_ids_class)]
                                                   }})
                                                   for x in REGION_INFO.names[prefix]])
                    settings.get('General', 'rendering_class').update(d)
            else:
                settings.set('Processing', '%s_classification' % prefix, False)
                settings.set('Processing', '%s_errorcorrection' % prefix, False)

        if has_timelapse:
            # generate raw images of selected channels (later used for gallery images)
            if settings.get('Output', 'events_export_gallery_images'):
                for prefix in ['primary', 'secondary', 'tertiary']:
                    if prefix == 'primary' or settings.get('Processing', '%s_processchannel' % prefix):
                        settings.get('General', 'rendering').update({prefix : {prefix.capitalize() :
                                                                               {'raw': ('#FFFFFF', 1.0)}}})
        else:
            # disable some tracking related settings in case no time-lapse data is present
            settings.set('Processing', 'tracking', False)
            settings.set('Processing', 'tracking_synchronize_trajectories', False)
            settings.set('Output', 'events_export_gallery_images', False)
            settings.set('Output', 'events_export_all_features', False)
            settings.set('Output', 'export_track_data', False)

        return settings
