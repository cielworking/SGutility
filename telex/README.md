# TeleX Static Site

Upload the contents of this folder to your website subdirectory:

```text
https://sgalerts.com/telex/
```

Recommended file layout on your site:

```text
/telex/index.html
/telex/download.html
/telex/privacy.html
/telex/terms.html
/telex/faq.html
/telex/support.html
/telex/style.css
/telex/TeleX.apk
```

After upload, update Supabase app_config:

```sql
update public.app_config
set
  latest_version_code = 1,
  minimum_version_code = 1,
  update_url = 'https://sgalerts.com/telex/download.html',
  privacy_url = 'https://sgalerts.com/telex/privacy.html',
  terms_url = 'https://sgalerts.com/telex/terms.html',
  faq_url = 'https://sgalerts.com/telex/faq.html',
  support_email = 'support@sgalerts.com',
  updated_at = now()
where id = true;
```

If you upload the APK with a different file name, update `download.html` accordingly.
