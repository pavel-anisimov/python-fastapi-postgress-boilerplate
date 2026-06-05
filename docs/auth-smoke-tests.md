# Auth Smoke Tests

These commands verify the Python FastAPI Auth/User service before connecting it through the Express API Gateway.

Base URL:

```bash
API_URL="http://localhost:8000"
MAILPIT_URL="http://localhost:8025"
TEST_EMAIL="pyuser$(date +%s)@example.com"
TEST_PASSWORD="Password123!"
NEW_PASSWORD="NewPassword123!"
```

## 1. Health

```bash
curl -s "$API_URL/health" | jq
```

Expected:

```json
{
  "status": "ok"
}
```

## 2. OpenAPI routes

```bash
curl -s "$API_URL/openapi.json" | jq '.paths | keys'
```

Expected to include:

```txt
/auth/register
/auth/login
/auth/logout
/auth/refresh
/auth/verify
/auth/resend-verification
/auth/forgot-password
/auth/reset-password
/users/me
```

## 3. Register

```bash
curl -i -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }"
```

Expected:

```txt
HTTP/1.1 200 OK
```

```json
{
  "ok": true,
  "message": "registration accepted; verification email sent"
}
```

Important: register should not return `access_token`.

## 4. Duplicate register

```bash
curl -i -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }"
```

Expected:

```txt
400 Bad Request
```

```json
{
  "detail": "Email already registered"
}
```

## 5. Login before email verification

```bash
curl -i -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }"
```

Expected:

```txt
403 Forbidden
```

```json
{
  "detail": "Email is not verified"
}
```

## 6. Get verification token from Mailpit

Open Mailpit:

```txt
http://localhost:8025
```

Find the verification email for `$TEST_EMAIL` and copy the token from the verification link.

The link should look like:

```txt
http://localhost:8000/auth/verify?token=<TOKEN>
```

Then export the token:

```bash
VERIFY_TOKEN="paste-token-here"
```

## 7. Verify email

```bash
curl -i -s "$API_URL/auth/verify?token=$VERIFY_TOKEN"
```

Expected:

```txt
200 OK
```

```json
{
  "ok": true,
  "message": "email verified"
}
```

## 8. Reusing verification token should fail

```bash
curl -i -s "$API_URL/auth/verify?token=$VERIFY_TOKEN"
```

Expected:

```txt
400 Bad Request
```

```json
{
  "detail": "Invalid or expired token"
}
```

## 9. Login after verification

```bash
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }")

echo "$LOGIN_RESPONSE" | jq

ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh_token')

echo "$ACCESS_TOKEN"
echo "$REFRESH_TOKEN"
```

Expected:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

## 10. Current user

```bash
curl -i -s "$API_URL/users/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Expected:

```txt
200 OK
```

Expected fields:

```json
{
  "id": 1,
  "email": "...",
  "is_active": true,
  "is_verified": true,
  "email_verified_at": "...",
  "roles": []
}
```

Should not include:

```txt
hashed_password
password
token
token_hash
refresh_token
```

## 11. Refresh access token

```bash
REFRESH_RESPONSE=$(curl -s -X POST "$API_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{
    \"refresh_token\": \"$REFRESH_TOKEN\"
  }")

echo "$REFRESH_RESPONSE" | jq

NEW_ACCESS_TOKEN=$(echo "$REFRESH_RESPONSE" | jq -r '.access_token')
```

Expected:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

## 12. Refresh with invalid token

```bash
curl -i -s -X POST "$API_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "not-a-real-refresh-token"
  }'
```

Expected:

```txt
401 Unauthorized
```

```json
{
  "detail": "Invalid refresh token"
}
```

## 13. Logout

```bash
curl -i -s -X POST "$API_URL/auth/logout" \
  -H "Authorization: Bearer $NEW_ACCESS_TOKEN"
```

Expected:

```txt
204 No Content
```

Expected body: empty.

Note: logout is currently stateless. It validates the bearer token but does not revoke JWTs server-side yet.

## 14. Forgot password

```bash
curl -i -s -X POST "$API_URL/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\"
  }"
```

Expected:

```txt
200 OK
```

```json
{
  "ok": true,
  "message": "if an account exists, a reset email has been sent"
}
```

## 15. Forgot password for unknown email

```bash
curl -i -s -X POST "$API_URL/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "unknown@example.com"
  }'
```

Expected: same safe response.

```json
{
  "ok": true,
  "message": "if an account exists, a reset email has been sent"
}
```

## 16. Get reset token from Mailpit

Open Mailpit:

```txt
http://localhost:8025
```

Find the reset password email for `$TEST_EMAIL` and copy the token from the reset link.

Then export:

```bash
RESET_TOKEN="paste-reset-token-here"
```

## 17. Reset password

```bash
curl -i -s -X POST "$API_URL/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d "{
    \"token\": \"$RESET_TOKEN\",
    \"password\": \"$NEW_PASSWORD\"
  }"
```

Expected:

```txt
200 OK
```

```json
{
  "ok": true,
  "message": "password has been reset"
}
```

## 18. Login with old password should fail

```bash
curl -i -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }"
```

Expected:

```txt
401 Unauthorized
```

```json
{
  "detail": "Invalid credentials"
}
```

## 19. Login with new password should succeed

```bash
curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$NEW_PASSWORD\"
  }" | jq
```

Expected:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

## 20. Resend verification for unknown email

```bash
curl -i -s -X POST "$API_URL/auth/resend-verification" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "unknown@example.com"
  }'
```

Expected:

```txt
200 OK
```

```json
{
  "ok": true,
  "message": "if an account exists and is not verified, a verification email has been sent"
}
```

## 21. Admin ping with normal user token

```bash
curl -i -s "$API_URL/admin/ping" \
  -H "Authorization: Bearer $NEW_ACCESS_TOKEN"
```

Expected for normal non-admin user:

```txt
403 Forbidden
```

## 22. Items smoke test

Create item:

```bash
curl -i -s -X POST "$API_URL/items" \
  -H "Authorization: Bearer $NEW_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Smoke test item",
    "description": "Created by auth smoke test"
  }'
```

List own items:

```bash
curl -i -s "$API_URL/items" \
  -H "Authorization: Bearer $NEW_ACCESS_TOKEN"
```

If item routes still use an older schema, this may fail. Auth integration does not depend on items.
