"""
                           The CellCognition Project
                     Copyright (c) 2006 - 2010 Michael Held
                      Gerlich Lab, ETH Zurich, Switzerland
                              www.cellcognition.org

              CellCognition is distributed under the LGPL License.
                        See trunk/LICENSE.txt for details.
                 See trunk/AUTHORS.txt for author contributions.
"""

__all__ = ['PluginManager',
           '_Plugin']

#-------------------------------------------------------------------------------
# standard library imports:
#
import os, \
       logging

#-------------------------------------------------------------------------------
# extension module imports:
#
from pdk.datetimeutils import StopWatch
from pdk.ordereddict import OrderedDict

#-------------------------------------------------------------------------------
# cecog module imports:
#

#-------------------------------------------------------------------------------
# constants:
#

#-------------------------------------------------------------------------------
# functions:
#

#-------------------------------------------------------------------------------
# classes:
#
class PluginManager(object):

    PREFIX = 'plugin'
    LABEL = ''

    def __init__(self, name, section):
        self.name = name
        self.section = section
        self._plugins = OrderedDict()
        self._instances = OrderedDict()
        self._observer = []

    def init_from_settings(self, settings):
        plugin_params = {}
        plugin_cls_names = {}

        self._instances.clear()

        for option_name in settings.options(self.section):
            items = option_name.split('__')
            if len(items) > 4 and items[0] == self.PREFIX and items[1] == self.name:
                plugin_cls_name = items[2]
                plugin_name = items[3]
                params = items[4]
                if not plugin_name in plugin_cls_names:
                    plugin_cls_names[plugin_name] = plugin_cls_name
                else:
                    assert plugin_cls_names[plugin_name] == plugin_cls_name
                plugin_params.setdefault(plugin_name, []).append((option_name, params))

        for plugin_name in plugin_params:
            plugin_cls_name = plugin_cls_names[plugin_name]
            plugin_cls = self._plugins[plugin_cls_name]
            trait_name_template = self._get_trait_name_template(plugin_cls_name, plugin_name)
            param_manager = \
                ParamManager.from_settings(plugin_cls, trait_name_template, settings, self.section,
                                           plugin_params[plugin_name])
            instance = plugin_cls(plugin_name, param_manager)
            self._instances[plugin_name] = instance
            self.notify_instance_modified(plugin_name)

        for observer in self._observer:
            observer.init()

    def add_instance(self, plugin_cls_name, settings):
        if not plugin_cls_name in self._plugins:
            raise ValueError("Plugin '%s' not registered for '%s'." % (plugin_cls_name, self.name))

        plugin_cls = self._plugins[plugin_cls_name]
        plugin_name = self._get_plugin_name(plugin_cls)
        trait_name_template = self._get_trait_name_template(plugin_cls_name, plugin_name)
        param_manager = ParamManager(plugin_cls, trait_name_template, settings, self.section)
        instance = plugin_cls(plugin_name, param_manager)
        self._instances[plugin_name] = instance
        self.notify_instance_modified(plugin_name)
        return plugin_name

    def remove_instance(self, plugin_name, settings):
        if not plugin_name in self._instances:
            raise ValueError("Plugin instance '%s' not found for '%s'." % (plugin_name, self.name))

        plugin = self._instances[plugin_name]
        plugin.close()
        del self._instances[plugin_name]
        self.notify_instance_modified(plugin_name, True)

    def notify_instance_modified(self, plugin_name, removed=False):
        pass

    def _get_plugin_name(self, plugin_cls):
        """
        generate new plugin name which is not used yet. starting at the plugin class NAME and appending numbers from
        2 to n, like 'primary', 'primary2', 'primary3'
        """
        cnt = 2
        result = plugin_cls.NAME
        while result in self._instances:
            result = plugin_cls.NAME + str(cnt)
            cnt += 1
        return result

    def _get_trait_name_template(self, plugin_cls_name, plugin_name):
        return '__'.join([self.PREFIX, self.name, plugin_cls_name, plugin_name, '%s'])

    def register_plugin(self, plugin_cls):
        self._plugins[plugin_cls.NAME] = plugin_cls

    def register_observer(self, observer):
        self._observer.append(observer)

    def get_plugin_cls_names(self):
        return self._plugins.keys()

    def get_plugin_labels(self):
        return [(name, cls.LABEL) for name, cls in self._plugins.iteritems()]

    def get_plugin_names(self):
        return sorted(self._instances.keys())

    def get_plugin_cls(self, name):
        return self._plugins[name]

    def get_plugin_instance(self, name):
        return self._instances[name]

    def run(self, *args, **options):
        results = OrderedDict()
        for instance in self._instances.itervalues():
            results[instance.name] = instance.run(*args, **options)
        return results


class ParamManager(object):

    GROUP_NAME = 'plugin'

    def __init__(self, plugin_cls, trait_name_template, settings, section, set_default=True):
        self._settings = settings
        self._section = section
        self._lookup = {}
        for param_name, trait in plugin_cls.PARAMS:
            trait_name = trait_name_template % param_name
            self._lookup[param_name] = trait_name
            settings.register_trait(section, self.GROUP_NAME, trait_name, trait)
            if set_default:
                settings.set(section, trait_name, trait.default_value)

    def remove_all(self):
        for trait_name in self._lookup.itervalues():
            self._settings.unregister_trait(self._section, self.GROUP_NAME, trait_name)

    def has_param(self, param_name):
        return param_name in self._lookup

    def get_trait_name(self, param_name):
        return self._lookup[param_name]

    def get_params(self):
        return self._lookup.items()

    @classmethod
    def from_settings(cls, plugin_cls, trait_name_template, settings, section, param_info):
        """
        register all traits for the given params to the settings manager
        """
        instance = cls(plugin_cls, trait_name_template, settings, section, False)
        for trait_name, param_name in param_info:
            if instance.has_param(param_name):
                value = settings.get_value(section, trait_name)
                settings.set(section, trait_name, value)
            else:
                raise ValueError("Parameter '%s' not specified." % param_name)
        return instance

    def __getitem__(self, param_name):
        return self._settings.get(self._section, self._lookup[param_name])

    def __setitem__(self, param_name, value):
        return self._settings.set(self._section, self._lookup[param_name], value)


class _Plugin(object):

    PARAMS = []
    NAME = None
    IMAGE = None
    DOC = None

    def __init__(self, name, param_manager):
        self.name = name
        self.param_manager = param_manager

    def close(self):
        self.param_manager.remove_all()

    @property
    def params(self):
        return self.param_manager

    def run(self):
        pass

    def render_to_gui(self, panel):
        """
        Defines how parameters are displayed to the GUI. panel is an instance of PluginParamFrame and implements the
        TraitDisplayMixin, which dynamically displays traits on a frame, which are connected to the settings instance
        (changes are traced and written to the .conf file)

        If not implemented by a plugin the parameters are displayed in one column sorted by appearance in PARAMS
        """
        raise NotImplementedError('This method must be implemented.')

