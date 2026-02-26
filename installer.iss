; installer.iss — Inno Setup script for TSG Builder (Windows)
;
; Builds a per-user installer that:
;   - Installs to {localappdata}\TSGBuilder (no admin rights required)
;   - Replaces app files on upgrade, preserves .env and .agent_ids.json
;   - Creates a Start Menu shortcut
;   - Registers in Add/Remove Programs
;
; CI passes the version via: ISCC installer.iss /DAppVersion=1.0.7
; For local testing:         ISCC installer.iss /DAppVersion=dev

#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
AppName=TSG Builder
AppVersion={#AppVersion}
AppPublisher=Jacob Centner
AppPublisherURL=https://github.com/jcentner/tsgbuilder
AppSupportURL=https://github.com/jcentner/tsgbuilder/issues
DefaultDirName={localappdata}\TSGBuilder
PrivilegesRequired=lowest
OutputBaseFilename=tsg-builder-windows-setup
UninstallDisplayName=TSG Builder
; No installer icon bundled yet — uses default
Compression=lzma2
SolidCompression=yes
; Allow user to pick a different directory if desired
DisableDirPage=no

[Files]
; Main executable
Source: "dist\tsg-builder-windows\tsg-builder-windows.exe"; DestDir: "{app}"; Flags: ignoreversion
; Bundled Python runtime + dependencies
Source: "dist\tsg-builder-windows\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentation
Source: "dist\tsg-builder-windows\GETTING_STARTED.md"; DestDir: "{app}"; Flags: ignoreversion
; Explicitly NOT including .env or .agent_ids.json — user config preserved by omission

[Icons]
Name: "{userprograms}\TSG Builder"; Filename: "{app}\tsg-builder-windows.exe"

[UninstallDelete]
; Clean up _internal directory on uninstall (Inno Setup normally handles this,
; but explicit entry ensures leftover .pyc / __pycache__ files are removed)
Type: filesandordirs; Name: "{app}\_internal"

[Code]
// Close any running TSG Builder instance before installing (upgrade scenario).
// The executable name is fixed, so we can search for it by window title or process.
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  // Attempt to kill any running instance — fail silently if none found
  Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
