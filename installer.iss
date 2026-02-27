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
; Stable AppId so Windows recognises upgrades even if AppName changes.
; The double {{ escapes the brace for Inno Setup.
AppId={{TSGBuilder}
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

[Run]
; Offer to launch TSG Builder after install finishes
Filename: "{app}\tsg-builder-windows.exe"; Description: "Launch TSG Builder"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up _internal directory on uninstall (Inno Setup normally handles this,
; but explicit entry ensures leftover .pyc / __pycache__ files are removed)
Type: filesandordirs; Name: "{app}\_internal"

[Code]

// --------------------------------------------------------------------------
//  Shared helper: kill tsg-builder-windows.exe and wait for the file handle
//  to be released.  Used by both install (PrepareToInstall) and uninstall
//  (CurUninstallStepChanged).  Returns True if the exe is unlocked (or was
//  never running), False if it is still locked after retries.
// --------------------------------------------------------------------------
function KillAndWaitForUnlock(): Boolean;
var
  ExePath: String;
  ResultCode: Integer;
  Retries: Integer;
begin
  Result := True;
  ExePath := ExpandConstant('{app}\tsg-builder-windows.exe');

  // Nothing to kill on a fresh install
  if not FileExists(ExePath) then
    Exit;

  // Kill any running instance
  Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);

  // Try to delete the exe to prove the file handle is released.
  // If deletion succeeds, Inno Setup (or the uninstaller) can proceed.
  Retries := 0;
  while Retries < 10 do
  begin
    if DeleteFile(ExePath) then
      Exit;   // File deleted — unlocked, good to proceed
    Sleep(1000);
    Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Retries := Retries + 1;
  end;

  // Still locked after ~10 seconds
  Result := False;
end;

// --------------------------------------------------------------------------
//  Install: runs right before file extraction.
// --------------------------------------------------------------------------
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  NeedsRestart := False;

  if not KillAndWaitForUnlock() then
    Result := 'Could not replace tsg-builder-windows.exe — it may still be running or locked by another program (e.g. antivirus).'
      + #13#10 + #13#10 + 'Please close TSG Builder and try again.';
end;

// --------------------------------------------------------------------------
//  Uninstall: kill the running app *before* the uninstaller tries to
//  delete files.  Without this, the exe and _internal DLLs remain locked
//  and the uninstaller shows "some files could not be removed".
//  CloseApplications only applies during install, not uninstall.
// --------------------------------------------------------------------------
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('taskkill', '/F /IM tsg-builder-windows.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
  end;
end;
