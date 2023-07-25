from distutils.core import setup
import glob
import os

ver = '0.0.1'
try:
    import subprocess
    ver = ver + '+' + subprocess.check_output(['git', 'describe', '--abbrev=8', '--always', '--dirty', '--tags']).decode().strip()
    print('Version is: %s' % ver)
except:
    print('Couldn\'t get version from git. Defaulting to %s' % ver)

# Generate a __version__.py file with this version in it
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'src', '__version__.py'), 'w') as fh:
    fh.write('__version__ = "%s"' % ver)

setup(name='mkid_readout',
      version='%s' % ver,
      description='Python libraries and scripts to control MKID readout firmware',
      author='Jack Hickish',
      author_email='jack@realtimeradio.co.uk',
      url='https://github.com/realtimeradio/souk-firmware',
      provides=['mkid_readout'],
      packages=['mkid_readout', 'mkid_readout.blocks'],
      package_dir={'mkid_readout' : 'src'},
      scripts=glob.glob('scripts/*.py'),
      )

if ver.endswith("dirty"):
    print("***************************************************")
    print("* You are installing from a dirty git repository. *")
    print("*          One day you will regret this.          *")
    print("*                                                 *")
    print("*      Consider cleaning up and reinstalling.     *")
    print("***************************************************")
