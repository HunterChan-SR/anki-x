#!/usr/bin/env python3
"""Optional native install entry points, built by each platform's toolchain."""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_x import __version__
from anki_x.platforms import system_id

system, cpu = system_id()
dist = ROOT / "dist"
payload = dist / "anki-x"
if system == "macos":
    app = dist / "Anki X.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    resources = contents / "Resources"
    resources.mkdir(exist_ok=True)
    shutil.copytree(payload, resources / "runtime", dirs_exist_ok=True)
    script = resources / "Start.command"
    script.write_text('#!/bin/sh\nset -eu\napp_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$app_dir/runtime/anki-x"\n')
    script.chmod(0o755)
    source = ROOT / "build/launcher.m"
    source.write_text('''#import <AppKit/AppKit.h>
int main(void) {
    @autoreleasepool {
        NSURL *script = [[NSBundle mainBundle] URLForResource:@"Start" withExtension:@"command"];
        if (script) { [[NSWorkspace sharedWorkspace] openURL:script]; }
    }
    return 0;
}
''')
    subprocess.run(["clang", "-framework", "AppKit", "-mmacosx-version-min=13.0", str(source), "-o", str(contents / "MacOS/AnkiX")], check=True)
    info = {"CFBundleName": "Anki X", "CFBundleDisplayName": "Anki X", "CFBundleExecutable": "AnkiX",
            "CFBundleIdentifier": "app.ankix.terminal", "CFBundleVersion": "1", "CFBundleShortVersionString": __version__,
            "CFBundlePackageType": "APPL", "LSMinimumSystemVersion": "13.0", "LSUIElement": True}
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    identity = os.environ.get("MACOS_SIGN_IDENTITY")
    if identity:
        subprocess.run(["codesign", "--force", "--deep", "--options", "runtime", "--timestamp", "--sign", identity, str(app)], check=True)
    dmgroot = dist / "dmg-root"
    dmgroot.mkdir(exist_ok=True)
    shutil.copytree(app, dmgroot / app.name, dirs_exist_ok=True)
    if not (dmgroot / "Applications").is_symlink():
        (dmgroot / "Applications").symlink_to("/Applications", target_is_directory=True)
    dmg = dist / f"anki-x-{__version__}-macos-{cpu}.dmg"
    subprocess.run(["hdiutil", "create", "-volname", "Anki X", "-srcfolder", str(dmgroot), "-ov", "-format", "UDZO", str(dmg)], check=True)
    print(dmg)
elif system == "windows":
    compiler = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    script = ROOT / "build/anki-x.iss"
    script.write_text(fr'''[Setup]
AppId=anki-x-terminal
AppName=anki-x
AppVersion={__version__}
DefaultDirName={{localappdata}}\Programs\anki-x-bootstrap
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir={dist}
OutputBaseFilename=anki-x-{__version__}-windows-{cpu}-setup
Compression=lzma2
SolidCompression=yes
Uninstallable=no
WizardStyle=modern
[Files]
Source: "{payload}\*"; DestDir: "{{tmp}}\anki-x-payload"; Flags: recursesubdirs createallsubdirs deleteafterinstall
[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not Exec(ExpandConstant('{{tmp}}\anki-x-payload\anki-x.exe'), 'install', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
      RaiseException('Could not start anki-x installer.');
    if ResultCode <> 0 then
      RaiseException('anki-x installation failed. Your previous installation was kept.');
  end;
end;
''', encoding="utf-8")
    subprocess.run([compiler, str(script)], check=True)
    print(dist / f"anki-x-{__version__}-windows-{cpu}-setup.exe")
else:
    print("Linux uses the verified install.sh / self-contained ZIP.")
