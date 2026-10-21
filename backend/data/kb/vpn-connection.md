# VPN Connection Issues
Category: Network

## Symptoms
- VPN client shows "Connection failed" or keeps reconnecting.
- Internal sites (intranet, file shares) do not open when working from home.

## Resolution steps
1. Check that your internet connection works by opening any public website.
2. Fully quit the VPN client (right-click the tray icon > Exit) and start it again.
3. Make sure you are connecting to the nearest gateway, e.g. `vpn-india.corp.example.com` when in India.
4. If you see "Certificate expired", restart your laptop while connected to the office network or open the Software Center and run "Refresh Device Certificate".
5. If MFA prompts do not arrive, see the MFA Setup article.

## Escalation
If the VPN still fails after these steps, raise a ticket with category **Network** and attach a screenshot of the error and the output of `ipconfig /all`.
