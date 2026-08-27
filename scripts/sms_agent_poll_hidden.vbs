' Launch sms_agent_poll.cmd with no visible console window.
' Task Scheduler runs this interactively (S4U needs an elevated prompt to set),
' and wscript with window style 0 keeps the 10-minute poll from flashing a
' console on the desktop. All output still lands in logs\sms_agent_poll.log.
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run """D:\SiftStack\scripts\sms_agent_poll.cmd""", 0, False
