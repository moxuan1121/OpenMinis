"""Check the built device app's deployment target and optional framework links.

Usage: python3 scripts/check_ios15_app.py build/Build/Products/Release-iphoneos/Minis.app
"""
import plistlib
import re
import subprocess
import sys
from pathlib import Path


def version(text):
    return tuple(map(int, text.split('.')))


def check(app):
    for extension in (app / 'PlugIns').glob('*.appex'):
        metadata = plistlib.loads((extension / 'Info.plist').read_bytes())
        assert version(metadata['MinimumOSVersion']) <= (15, 6, 0), (
            'Unsupported extension in iOS 15 package', extension.name, metadata['MinimumOSVersion'])
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    assert info['MinimumOSVersion'] == '15.6', info['MinimumOSVersion']
    executable = app / info['CFBundleExecutable']
    commands = subprocess.check_output(['xcrun', 'otool', '-l', str(executable)], text=True)
    # minos is used by LC_BUILD_VERSION; older binaries use LC_VERSION_MIN_IPHONEOS.
    minimums = re.findall(r'\bminos\s+(\d+\.\d+(?:\.\d+)?)', commands) or re.findall(
        r'cmd LC_VERSION_MIN_IPHONEOS\s+cmdsize \d+\s+version (\d+\.\d+(?:\.\d+)?)', commands)
    assert minimums and all(version(v) <= (15, 6, 0) for v in minimums), minimums
    for block in re.split(r'Load command \d+', commands):
        if any('/' + name + '.framework/' in block for name in ['ActivityKit', 'AppIntents', 'WeatherKit']):
            assert 'cmd LC_LOAD_WEAK_DYLIB' in block, 'Required framework on iOS 15: ' + block
    for bundle in [app, *(app / 'PlugIns').glob('*.appex')]:
        entitlements = plistlib.loads(subprocess.check_output(
            ['codesign', '-d', '--entitlements', '-', '--xml', str(bundle)], stderr=subprocess.DEVNULL))
        assert 'group.com.openminis.app' in entitlements.get('com.apple.security.application-groups', []), (
            'App Group entitlement missing', bundle.name)
    print('PASS: iOS 15.6 binary/package compatibility and preserved App Group entitlements')


if __name__ == '__main__':
    check(Path(sys.argv[1]))
