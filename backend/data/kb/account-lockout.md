# Account Locked Out
Category: Access

## Why accounts lock
Your account locks for 30 minutes after 10 failed sign-in attempts. Common causes are an old password saved on a phone (email app) or a mapped network drive.

## Resolution steps
1. Wait 30 minutes; the lock clears automatically.
2. Update the saved password on all devices: phone mail app, tablet, and Windows Credential Manager.
3. If you need access urgently, use the self-service portal to unlock: `https://passwordreset.corp.example.com` > "Unlock account".

## Escalation
If the account keeps locking after updating all devices, raise an **Access** ticket with priority High. The team can check the domain controller logs to find the device that sends the wrong password.
