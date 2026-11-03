# Microsoft Entra ID — Setup Guide

## Step 1: Create an App Registration

1. Sign in to [portal.azure.com](https://portal.azure.com)
2. Go to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Fill in:
   - **Name:** `Milo Integration` (or any name)
   - **Supported account types:** 
     - For personal use: *Accounts in any organizational directory and personal Microsoft accounts*
     - For work-only: *Accounts in this organizational directory only*
   - **Redirect URI:** Leave empty (Device Code Flow does not need one)
5. Click **Register**

## Step 2: Get the Client ID

On the overview page, copy the **Application (client) ID**.

Set this as `MICROSOFT_CLIENT_ID` in `.env.microsoft`.

## Step 3: Enable Public Client (Device Code Flow)

1. Go to **Authentication** in the app registration
2. Scroll to **Advanced settings**
3. Set **Allow public client flows** to **Yes**
4. Click **Save**

> Device Code Flow is a *public client* flow — no client secret is needed.

## Step 4: Add API Permissions

1. Go to **API permissions** → **Add a permission**
2. Select **Microsoft Graph** → **Delegated permissions**
3. Add the following:
   - `User.Read`
   - `Calendars.ReadWrite`
   - `Tasks.ReadWrite`
   - `offline_access` (usually pre-added)
4. Click **Add permissions**

> For personal Microsoft accounts (`common` tenant), user consent is sufficient.
> For corporate/work tenants, an admin may need to grant tenant-wide consent.

## Step 5: Admin Consent (Corporate Tenants Only)

If you are using a work or school account:

1. Go to **API permissions**
2. Click **Grant admin consent for [Your Organization]**
3. Confirm

> If you don't have admin rights, send the Application (client) ID to your IT administrator
> and ask them to grant consent via:
> `https://login.microsoftonline.com/{tenant}/adminconsent?client_id={client_id}`

## Step 6: Configure Environment Variables

Copy the example file:

```bash
cp microsoft_integration/.env.microsoft.example microsoft_integration/.env.microsoft
```

Edit `.env.microsoft`:

```env
MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MICROSOFT_TENANT=common
```

Use `common` unless you know your tenant ID:
- `common` — Works for both personal and work accounts
- `consumers` — Personal Microsoft accounts only
- `organizations` — Work/school accounts only
- `{tenant-id}` — Specific tenant only

## Step 7: Generate the Encryption Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Output example:
```
Z0FBQUFBQnlHMVg4...
```

Set this as `MICROSOFT_TOKEN_ENCRYPTION_KEY` in `.env.microsoft`.

**⚠️ This key encrypts your Microsoft access tokens. Never:**
- Share it with others
- Commit it to Git
- Store it in plain text

## Step 8: Start the Service

```bash
cd /path/to/milo_2
uvicorn microsoft_integration.main:app --host 0.0.0.0 --port 8010
```

Or:

```bash
python -m microsoft_integration.main
```

## Step 9: Connect Your Account

1. Open **http://localhost:8010/microsoft**
2. Click **Conectar cuenta**
3. A popup shows a URL and a short code
4. Open the URL in any browser and enter the code
5. Sign in with your Microsoft account
6. Authorize the Milo Integration app
7. Return to the Milo panel — the account will appear as **Conectada**

## Permissions Summary

| Permission | Why |
|-----------|-----|
| `User.Read` | Display user profile and email in the Milo UI |
| `Calendars.ReadWrite` | Read and write Outlook Calendar events |
| `Tasks.ReadWrite` | Read and write Microsoft To Do tasks |
| `offline_access` | Refresh tokens without re-prompting the user |

## Permissions NOT Requested

Milo explicitly does NOT request:
- `Mail.Read` / `Mail.ReadWrite` — emails
- `Files.Read` / `Files.ReadWrite` — OneDrive files
- `Contacts.ReadWrite` — contacts
- `Directory.ReadWrite.All` — directory management
- Any Teams or SharePoint permissions

## Troubleshooting App Registration

| Error | Solution |
|-------|----------|
| `AADSTS65005 - app not found` | Check client ID is correct |
| `AADSTS7000218 - public client flow not enabled` | Enable public client flows in Authentication settings |
| `AADSTS65001 - user consent required` | User must consent during Device Code Flow |
| `AADSTS700082 - refresh token expired` | Re-authenticate via Device Code Flow |
| `insufficient_scope` | Verify all three Graph permissions are added |
