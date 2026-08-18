from setuptools import setup
from os import path

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='cbpi4-ESPHome',
      version='0.0.1',
      description='CraftBeerPi4 ESPHome Plugin (native API, sensors + actors, no Home Assistant required)',
      author='Arco Veenhuizen',
      author_email='info@veenhuizen.net',
      url='https://github.com/arcidodo/cbpi4-ESPHome',
      license='GPLv3',
      include_package_data=True,
      package_data={
                  '': ['*.txt', '*.rst', '*.yaml'],
                  'cbpi4-ESPHome': ['*', '*.txt', '*.rst', '*.yaml']},
      packages=['cbpi4-ESPHome'],
      install_requires=[
            'cbpi4>=4.0.0.34',
            'aioesphomeapi>=17.0.0',
      ],
      long_description=long_description,
      long_description_content_type='text/markdown'
      )