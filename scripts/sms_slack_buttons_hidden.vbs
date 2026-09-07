' Launch sms_slack_buttons.cmd with no visible console window.
' Same reasoning as sms_agent_poll_hidden.vbs: Task Scheduler runs this
' interactively (S4U needs an elevated prompt to set), and this listener stays
' up for days, so a visible console would sit on the desktop permanently.
' All output still lands in logs\sms_slack_buttons.log.
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run """D:\SiftStack\scripts\sms_slack_buttons.cmd""", 0, False
