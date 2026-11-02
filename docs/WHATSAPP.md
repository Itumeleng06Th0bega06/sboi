# WhatsApp notifications

WhatsApp delivery is **optional**. The project does not bundle or simulate a
WhatsApp provider. In-app notifications always work; WhatsApp is attempted only
when all three conditions below are true.

1. A provider endpoint and token are configured.
2. The membership record has `whatsapp_consent = True`.
3. The membership has a phone number with at least 7 digits.

If any condition is missing, the review records an honest status and the site
never claims a message was delivered.

WhatsApp notices are deliberately generic: they only tell the member that
something needs their attention and send them to the private inbox. Message
text, decision details, admin notes and attachments are never sent to the
provider.

## Where it runs

`members.services.apply_membership_decision()` is the only place that changes a
membership approval. After the in-app notification is written it calls
`send_membership_whatsapp()`, which:

- posts a JSON body to `WHATSAPP_API_URL`;
- stores `whatsapp_status` and `whatsapp_error` on the
  `MembershipChangeRequest` row;
- never raises into the admin request if the provider is down.

`members.services.notify_member_reply()` does the same for a private inbox
message. Its optional notice is sent by `send_message_whatsapp()`, and the
result is stored on the `notifications.Notification` row instead of a review
request.

The admin review queue and review page show both fields, so staff can see
exactly what happened.

## Required settings

| Setting | Meaning |
| --- | --- |
| `WHATSAPP_API_URL` | Full HTTPS endpoint for a single text message. |
| `WHATSAPP_API_TOKEN` | Bearer token/API key for that endpoint. |
| `WHATSAPP_SENDER_ID` | Optional sender id or phone-number id; included as `"from"` when set. |

Development defaults are blank in `sboi/settings.py`. Production reads the same
names from `.env` in `sboi/settings_prod.py`. Add them to the production `.env`:

```dotenv
WHATSAPP_API_URL=https://graph.facebook.com/v20.0/YOUR_PHONE_NUMBER_ID/messages
WHATSAPP_API_TOKEN=your-permanent-provider-token
WHATSAPP_SENDER_ID=
```

Keep the token in `.env` (already git-ignored). Never put it in a template,
JavaScript file, or committed settings value.

## Request shape

```http
POST <WHATSAPP_API_URL>
Authorization: Bearer <WHATSAPP_API_TOKEN>
Content-Type: application/json

{
  "to": "27821234567",
  "type": "text",
  "text": { "body": "Your church membership record has an update. Sign in to your account to view the details." },
  "from": "<WHATSAPP_SENDER_ID, only when set>"
}
```

The inbox notice uses the same shape with the body: "You have a new private
message from the Shekinah Blaze church administration. Sign in to your account
to read and reply."

The phone value is the membership number with every non-digit removed. The
function does **not** guess a country code, so store the full international
number (for example `27821234567`) on the membership record.

The default payload follows the Meta WhatsApp Cloud API text-message shape. If
your provider expects a different contract (Twilio, BulkSMS, an internal
gateway), adapt `send_membership_whatsapp()` in `members/services.py` and keep
the same status/error handling.

## Delivery statuses

| Status | Meaning |
| --- | --- |
| `not_attempted` | Default before a review decision. |
| `not_configured` | URL or token is blank; no network call was made. |
| `skipped` | No consent, or no usable phone number. |
| `sent` | The provider returned HTTP 2xx. |
| `failed` | A network error, timeout, or non-2xx response; `whatsapp_error` holds the reason (truncated to 500 characters). |

`not_configured` is the expected result on a fresh install. It is not an error
and does not block the membership decision.

## Testing safely

- With the settings blank, approve a test membership and confirm the review row
  says **Not configured** and no outbound request was made.
- With consent off, confirm **Skipped (no consent or phone)**.
- To test a real provider, point `WHATSAPP_API_URL` at a staging endpoint or a
  local mock server that accepts the JSON above. Use a test phone number and a
  test token; do not send to a real member without consent.
- The call uses a 10 second timeout. A failing provider must leave the
  membership decision committed and the in-app notification intact.

## Privacy and safety

- WhatsApp is only sent when the member explicitly opted in on their membership
  record. Consent can be withdrawn at any time by editing membership details.
- The notice is generic. It never contains the decision title, admin note,
  private message text, attachment name, or the full message thread. Members
  sign in to read confidential content.
- The endpoint must be HTTPS. Do not log the token or the full provider
  response body.
- Provider rate limits, template rules, and opt-in requirements are the
  deployment's responsibility. This project does not bypass them.
