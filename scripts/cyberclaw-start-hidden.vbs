Set shell = CreateObject("WScript.Shell")
shell.Run "cmd /c """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\cyberclaw-start.cmd""", 0, False
