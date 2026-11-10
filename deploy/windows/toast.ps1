# Shows one Windows toast titled SILVR with the given message: no buttons, no actions.
# Run with Windows PowerShell 5.1 (powershell.exe), NOT pwsh 7: only 5.1 has the WinRT toast
# types. It borrows Windows PowerShell's own AppUserModelID so no shortcut or module is needed.
# The message goes in as a DOM text node, which escapes & < > for the toast XML.
param([Parameter(Mandatory)][string]$Message)
$ErrorActionPreference = 'Stop'
$aumid = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $xml.GetElementsByTagName('text')
$null = $text.Item(0).AppendChild($xml.CreateTextNode('SILVR'))
$null = $text.Item(1).AppendChild($xml.CreateTextNode($Message))
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aumid).Show($toast)
