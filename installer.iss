; installer.iss — Inno Setup script for TSG Builder (Windows)
;
; Builds a per-user installer that:
;   - Installs to {localappdata}\TSGBuilder (no admin rights required)
;   - Replaces app files on upgrade, preserves .env and .agent_ids.json
;   - Creates Start Menu and Desktop shortcuts
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
DisableProgramGroupPage=yes
; Force-close running TSG Builder via Restart Manager before replacing files
CloseApplications=force
RestartApplications=no

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
Name: "{userdesktop}\TSG Builder"; Filename: "{app}\tsg-builder-windows.exe"

[UninstallDelete]
; Clean up _internal directory on uninstall (Inno Setup normally handles this,
; but explicit entry ensures leftover .pyc / __pycache__ files are removed)
Type: filesandordirs; Name: "{app}\_internal"

[Code]
// Runs right before file extraction. Kills TSG Builder if running and
// proves the exe is unlocked by deleting it. If the file is still locked
// after retries, returns an error string that aborts the install.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExePath: String;
  ResultCode: Integer;
  Retries: Integer;
begin
  Result := '';
  NeedsRestart := False;

  ExePath := ExpandConstant('{app}\tsg-builder-windows.exe');

  // Fresh install — nothing to replace
  if not FileExists(ExePath) then
    Exit;

  // Kill any running instance
  Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);

  // Try to delete the old exe to prove the file handle is released.
  // If deletion succeeds, Inno Setup will write the new one normally.
  Retries := 0;
  while Retries < 10 do
  begin
    if DeleteFile(ExePath) then
      Exit;  // File deleted — unlocked, good to proceed
    Sleep(1000);
    // Retry kill in case handle is still held
    Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Retries := Retries + 1;
  end;

  // Still locked after ~10 seconds — abort with a clear message
  Result := 'Could not replace tsg-builder-windows.exe — it may still be running or locked by another program (e.g. antivirus).'
    + #13#10 + #13#10 + 'Please close TSG Builder and try again.';
end;
