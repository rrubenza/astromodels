__author__ = 'giacomov'

__doc__ = """
=============
Description
=============

Models in astromodels are defined with a language as closest as possible to the natural language. In the definition of
the model, which happens only once in any given analysis, the syntax is very explicit and analytical, while the use of
the Model class is geared towards usability.

This is an example of a simple likelihood model, with one point source having two spectral components, both with
a powerlaw shape but the first with a linear polarization, the second with a circular polarization::

  test_source :

      point source:

          position:

              RA : {value: 23.5}
              Dec : {value: -45.4}

          spectrum :

              main :

                  shape:

                      powerlaw :

                          logK : {value: 1}
                          index : {value: -2}
                          piv : {value: 100, unit: 'keV'}

                  polarization :

                      linear :

                         degree : {value: 0.2}
                         angle : {value: 45}

              other :

                  shape:

                      powerlaw :

                          logK : {value: 1}
                          index : {value: -2}
                          piv : {value: 200}

                  polarization :

                      stokes:

                          I : {value : 1}
                          Q : {value : 0}
                          U : {value : 0}
                          V : {value : 1}

This model can be read like this:

  > mp = model_parser.ModelParser('test.yml')
  > mod = m.get_model()

Now mod is a instance of a Model, and parameters can be accessed like::

  > ra = mod.test_source.position.RA
  > dec = mod.test_source.position.Dec
  > logK = mod.test_source.main.shape.logK
  > I = mod.test_source.other.polarization.I

Although perhaps a more natural way would have been "mod.test_source.spectrum.main.shape.powerlaw.logK, this would have
resulted in a very long sequence. Thus, all redundant expressions have been removed.

"""

from astromodels import sky_direction
from astromodels.functions import function
from astromodels import spectral_component
from astromodels import polarization
from astromodels.sources import point_source
from astromodels import parameter
from astromodels import model
from astromodels.my_yaml import my_yaml
from astromodels.sources.point_source import POINT_SOURCE
from astromodels.sources.extended_source import EXTENDED_SOURCE
import re

class ModelIOError(IOError):
    pass


class ModelYAMLError(my_yaml.YAMLError):
    pass


class ModelSyntaxError(RuntimeError):
    pass


def load_model(filename):
    """
    Load a model from a file.

    :param filename: the name of the file containing the model
    :return: an instance of a Model
    """

    parser = ModelParser(filename)

    return parser.get_model()


class ModelParser(object):
    def __init__(self, model_file):

        # Read model file and deserialize into a dictionary

        try:

            with open(model_file) as f:

                self._model_dict = my_yaml.load(f)

        except IOError:

            raise ModelIOError("File %s cannot be read. Check path and permissions for current user." % model_file)

        except my_yaml.YAMLError:

            raise ModelYAMLError("Could not parse file %s. Check your syntax." % model_file)

        self._parse()

    def _parse(self):

        # Traverse the dictionary and create all the needed classes

        # The first level is the source level

        self._sources = []
        self._independent_variables = []
        self._links = []

        for source_or_var_name, source_or_var_definition in self._model_dict.iteritems():

            if source_or_var_name.find("(IndependentVariable)") > 0:

                var_name = source_or_var_name.split("(")[0].replace(" ","")

                this_parser = IndependentVariableParser(var_name, source_or_var_definition)

                self._independent_variables.append(this_parser.get_variable())

            else:

                this_parser = SourceParser(source_or_var_name, source_or_var_definition)

                self._sources.append(this_parser.get_source())

                self._links.extend(this_parser.links)



    def get_model(self):

        # Instance the model with all the parsed sources

        new_model = model.Model(*self._sources)

        # Now set up IndependentVariable instances (if any)

        for independent_variable in self._independent_variables:

            new_model.add_independent_variable(independent_variable)

        # Now set up the links

        for link in self._links:

            path = link['parameter_path']
            variable = link['variable']
            law = link['law']

            new_model[path].add_auxiliary_variable(new_model[variable],law)

        return new_model


class IndependentVariableParser(object):

    def __init__(self, name, definition):

        self._variable = parameter.IndependentVariable(name, **definition)

    def get_variable(self):

        return self._variable


class SourceParser(object):
    def __init__(self, source_name, source_definition):

        # Get the type of the source

        try:

            # Point source or extended source?

            source_type = re.findall('\((%s|%s)\)' % (POINT_SOURCE, EXTENDED_SOURCE), source_name)[-1]

        except IndexError:

            raise ModelSyntaxError("Don't recognize type for source '%s'. "
                                   "Valid types are '%s' or '%s'." %
                                   (source_name, POINT_SOURCE, EXTENDED_SOURCE))

        else:

            # Strip the source_type from the name

            source_name = source_name.split()[0]

        self._source_name = source_name

        # This will store the links (if any)
        self._links = []

        if source_type == POINT_SOURCE:

            self._parsed_source = self._parse_point_source(source_definition)

        elif source_type == EXTENDED_SOURCE:

            self._parsed_source = self._parse_extended_source(source_definition)

    @property
    def links(self):

        return self._links

    def get_source(self):

        return self._parsed_source

    def _parse_point_source(self, pts_source_definition):

        # Parse the positional information

        try:

            position_definition = pts_source_definition['position']

        except KeyError:

            raise ModelSyntaxError("Point source %s is missing the 'position' attribute" % self._source_name)

        this_sky_direction = self._parse_sky_direction(position_definition)

        # Parse the spectral information

        try:

            spectrum = pts_source_definition['spectrum']

        except KeyError:

            raise ModelSyntaxError("Point source %s is missing the 'spectrum' attribute" % self._source_name)

        components = []

        for component_name, component_definition in pts_source_definition['spectrum'].iteritems():
            this_component = self._parse_spectral_component(component_name, component_definition)

            components.append(this_component)

        this_point_source = point_source.PointSource(self._source_name, sky_position=this_sky_direction,
                                                     components=components)

        return this_point_source

    def _parse_sky_direction(self, sky_direction_definition):

        # Instance the SkyDirection class using the coordinates provided

        coordinates = {}

        if 'ra' in sky_direction_definition and 'dec' in sky_direction_definition:

            ra = parameter.Parameter('ra', sky_direction_definition['ra']['value'])
            ra.set_bounds(0, 360)
            ra.fix = True

            dec = parameter.Parameter('dec', sky_direction_definition['dec']['value'])
            dec.set_bounds(-90, 90)
            dec.fix = True

            coordinates['ra'] = ra
            coordinates['dec'] = dec

        elif 'l' in sky_direction_definition and 'b' in sky_direction_definition:

            l = parameter.Parameter('l', sky_direction_definition['l']['value'])
            l.set_bounds(0, 360)
            l.fix = True

            b = parameter.Parameter('b', sky_direction_definition['b']['value'])
            b.set_bounds(-90, 90)
            b.fix = True

            coordinates['l'] = l
            coordinates['b'] = b

        else:

            raise ModelSyntaxError("Position specification for source %s has an invalid coordinate pair. "
                                   " You need to specify either 'ra' and 'dec', or 'l' and 'b'."
                                   % self._source_name)

        # Check if there is a equinox specification

        if 'equinox' in sky_direction_definition:
            coordinates['equinox'] = sky_direction_definition['equinox']

        try:

            this_sky_direction = sky_direction.SkyDirection(**coordinates)

        except sky_direction.WrongCoordinatePair:

            raise ModelSyntaxError("Position specification for source %s has an invalid coordinate pair"
                                   % self._source_name)

        return this_sky_direction

    def _parse_spectral_component(self, component_name, component_definition):

        # Parse the shape definition, which is the first to occur

        try:

            function_name = component_definition.keys()[0]
            parameters_definition = component_definition[function_name]

        except KeyError:

            raise ModelSyntaxError("The component %s of source %s is malformed"
                                   % (component_name, self._source_name))

        shape = self._parse_shape_definition(component_name, function_name, parameters_definition)

        this_polarization = polarization.Polarization()

        this_spectral_component = spectral_component.SpectralComponent(component_name, shape, this_polarization)

        return this_spectral_component

    def _parse_shape_definition(self, component_name, function_name, parameters_definition):

        # Get the function

        try:

            function_instance = function.get_function(function_name)

        except AttributeError:

            raise ModelSyntaxError("Function %s, specified as shape for component %s of source %s, is not a "
                                   "known 1d function" % (function_name, component_name, self._source_name))

        # Loop over the parameters of the function instance, instead of the specification,
        # so we can understand if there are parameters missing from the specification

        for parameter_name in function_instance.parameters.keys():

            try:

                this_definition = parameters_definition[parameter_name]

            except KeyError:

                raise ModelSyntaxError("Function %s, specified as shape for component %s of source %s, lacks "
                                       "the definition for parameter %s"
                                       % (function_name, component_name, self._source_name, parameter_name))

            # Update the parameter. Note that the order is important, because trying to set the value before the
            # minimum and maximum could result in a error.

            # All these specifications are optional. If they are not present, then the default value
            # already contained in the instance of the function will be used

            if 'min' in this_definition:
                function_instance.parameters[parameter_name].min_value = this_definition['min']

            if 'max' in this_definition:
                function_instance.parameters[parameter_name].max_value = this_definition['max']

            if 'delta' in this_definition:
                function_instance.parameters[parameter_name].delta = this_definition['delta']

            if 'fix' in this_definition:
                function_instance.parameters[parameter_name].fix = this_definition['fix']

            if 'free' in this_definition:
                function_instance.parameters[parameter_name].free = this_definition['free']

            if 'unit' in this_definition:
                function_instance.parameters[parameter_name].unit = this_definition['unit']

            # Now set the value, which must be present

            if 'value' not in this_definition:

                raise ModelSyntaxError("The parameter %s in function %s, specified as shape for component %s "
                                       "of source %s, lacks a 'value' attribute"
                                       % (parameter_name, function_name, component_name, self._source_name))

            # Check if this is a linked parameter, i.e., if 'value' is something like f(source.spectrum.powerlaw.index)

            matches = re.findall('''f\((.+)\)''', str(this_definition['value']))

            if matches:

                # This is an expression which marks a parameter
                # with a link to another parameter (or an IndependentVariable such as time)

                # Get the variable
                linked_variable = matches[0]

                # Now get the law

                if 'law' not in this_definition:

                    raise ModelSyntaxError("The parameter %s in function %s, specified as shape for component %s "
                                           "of source %s, is linked to %s but lacks a 'law' attribute"
                                           % (parameter_name, function_name, component_name,
                                              self._source_name, linked_variable))

                link_function_name = this_definition['law'].keys()[0]

                link_function_instance = self._parse_shape_definition(component_name, link_function_name,
                                                                      this_definition['law'][link_function_name])

                path = ".".join([self._source_name, 'spectrum', component_name, function_name, parameter_name])

                self._links.append( {'parameter_path': path,
                                     'law': link_function_instance,
                                     'variable': linked_variable} )

            else:

                # This is a normal (not linked) parameter

                function_instance.parameters[parameter_name].value = this_definition['value']




        return function_instance

    def _parse_extended_source(self, ext_source_definition):

        return 0
