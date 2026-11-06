# Register an ORCID sandbox client

The sandbox is separate from the production ORCID registry. Test accounts and client credentials created there are for testing only. The application uses the Public API's sign-in capability, so start with a **sandbox Public API client**. Check whether your institution already has an appropriate client or ORCID membership before establishing a long-term production integration.

1. Go to [ORCID sandbox registration](https://sandbox.orcid.org/register) and create a sandbox account, then sign in. ORCID's [sandbox instructions](https://info.orcid.org/documentation/integration-guide/getting-started-with-your-orcid-integration/) say sandbox verification mail is delivered only to `@mailinator.com` addresses. Mailinator public inboxes are accessible to others: use them only for disposable sandbox identities, and never put real personal or confidential information in them.
2. Verify the sandbox account's email, then open [sandbox Developer Tools](https://sandbox.orcid.org/developer-tools), or select **Developer Tools** from your name menu. Read and accept the Public API terms and select **Register for ORCID Public API Credentials**. The interface wording may vary.
3. Complete the application form. For example, use **CCI Dashboard Test** as the name, `https://dashboard-django-test.apps.k8s.gu.se/` as the application URL, and describe that the test dashboard uses sandbox ORCID sign-in to request administrator-approved access. Check that the proposed hostname is accepted by your cluster before relying on it.
4. Add this complete redirect URI, including its trailing slash:

   `https://dashboard-django-test.apps.k8s.gu.se/accounts/orcid/login/callback/`

   If your actual Route hostname changes, register its matching callback instead and update both the Route and Django ConfigMap. The Route does not need to exist merely to enter a callback, but it must be reachable from an allowed browser to complete a login test.
5. Save the application and generate the **client ID** and **client secret**. In OpenShift project `core-omero-test`, create the `dashboard-django-app` Opaque Secret with `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET` set to these sandbox credentials, plus a new random `DJANGO_SECRET_KEY`. Do not post the client secret in chat or commit it to Git.
6. Leave `ORCID_ENVIRONMENT` set to `sandbox` in the Django ConfigMap. After deployment, sign in with a sandbox account from an allowed network. First sign-in should produce a pending dashboard account. For an approval test, create a second disposable sandbox identity. Real production ORCID accounts and production client credentials do not work as sandbox credentials.

See ORCID's [Public API client registration guide](https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/) for the current form and terms. ORCID says Public API credentials are tied to an individual's record and are not transferable; establish an institutionally appropriate owner and production-credentials plan before production.
