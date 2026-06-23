RIDERLINK EMAIL CONFIRMATION PAGE

1. Copy the folder:
   riderlink-confirmed

   into the root of your SGAlerts GitHub Pages repository.

2. Commit and push the files.

3. Confirm that this URL opens:
   https://sgalerts.com/riderlink-confirmed/

4. In Supabase go to:
   Authentication -> URL Configuration

5. For the simplest current setup, use:

   Site URL:
   https://sgalerts.com/riderlink-confirmed/

   Redirect URLs:
   https://sgalerts.com/riderlink-confirmed/

6. Save the settings and register a fresh test account.

The confirmation page is static and does not require JavaScript, a database,
or any changes to your Flutter dependencies.

Later, when RiderLink supports mobile deep links or password reset pages, the
Site URL can be changed to a general RiderLink website and the individual auth
flows can use their own redirect URLs.
