from setuptools.command.test import test as TestCommand
import setuptools
import io
import sys

class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True
    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


setuptools.setup(
    name='MultiAlchemy',
    version='0.1.0',
    description='Row-based multitenancy for SQLAlchemy',
    author='Michael White',
    author_email='m@mwhite.info',
    url='http://github.com/mwhite/MultiAlchemy',
    license='MIT License',
    packages=['multialchemy'],
    test_suite='tests',
    install_requires=io.open('requirements.txt').read().splitlines(),
    tests_require=['pytest'],
    cmdclass = {'test': PyTest},
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7'
        'Topic :: Database',
    ],
)

