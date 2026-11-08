import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='native macOS bridge')


def test_native_float_message_accepts_foundation_dictionary(monkeypatch):
    monkeypatch.setenv("MEETING_INTERPRETER_MODE", "mock")
    from Foundation import NSDictionary
    from meeting_interpreter.desktop import _NativeAppDelegate

    calls = []

    class RecordingDelegate(_NativeAppDelegate):
        def setFloating_(self, enabled):
            calls.append(bool(enabled))

    delegate = RecordingDelegate.alloc().initWithURL_('http://127.0.0.1:8000')
    delegate.handleNativeMessage_(NSDictionary.dictionaryWithDictionary_({'type': 'floating', 'enabled': True}))
    assert calls == [True]


def test_native_export_saves_chinese_text_to_selected_file(monkeypatch, tmp_path):
    monkeypatch.setenv('MEETING_INTERPRETER_MODE', 'mock')
    from Foundation import NSDictionary
    import meeting_interpreter.desktop as desktop

    destination = tmp_path / '会议字幕.txt'

    class SavePanel:
        def setNameFieldStringValue_(self, value):
            assert value == 'meeting.txt'

        def setCanCreateDirectories_(self, value):
            pass

        def setMessage_(self, value):
            pass

        def runModal(self):
            return desktop.NSModalResponseOK

        def URL(self):
            return type('URL', (), {'path': lambda self: str(destination)})()

    class Panels:
        @staticmethod
        def savePanel():
            return SavePanel()

    monkeypatch.setattr(desktop, 'NSSavePanel', Panels, raising=False)
    delegate = desktop._NativeAppDelegate.alloc().initWithURL_('http://127.0.0.1:8000')
    delegate.handleNativeMessage_(NSDictionary.dictionaryWithDictionary_({
        'type': 'export_transcript', 'filename': 'meeting.txt', 'text': '会议原文\n会議の翻訳',
    }))
    assert destination.read_text(encoding='utf-8') == '会议原文\n会議の翻訳'


def test_native_appearance_bridge_switches_light_dark_and_system(monkeypatch):
    from Foundation import NSDictionary
    import meeting_interpreter.desktop as desktop
    calls = []
    class Application:
        @staticmethod
        def sharedApplication():
            return Application()
        def setAppearance_(self, appearance):
            calls.append(appearance)
    class Appearance:
        @staticmethod
        def appearanceNamed_(name):
            return name
    monkeypatch.setattr(desktop, 'NSApplication', Application)
    monkeypatch.setattr(desktop, 'NSAppearance', Appearance)
    delegate = desktop._NativeAppDelegate.alloc().initWithURL_('http://127.0.0.1:8000')
    for mode in ['light', 'dark', 'system', 'invalid']:
        delegate.handleNativeMessage_(NSDictionary.dictionaryWithDictionary_({'type':'appearance','mode':mode}))
    assert calls == [desktop.NSAppearanceNameAqua, desktop.NSAppearanceNameDarkAqua, None]
