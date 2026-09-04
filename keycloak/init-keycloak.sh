#!/bin/sh
set -eu

KCADM=/opt/keycloak/bin/kcadm.sh
REALM=health-interop
IMPORT_FILE=/opt/keycloak-init/health-interop-realm.json

authenticated=false
attempt=0
while [ "$attempt" -lt 60 ]; do
  attempt=$((attempt + 1))
  if "$KCADM" config credentials \
    --server http://keycloak:8080 \
    --realm master \
    --user "$KEYCLOAK_ADMIN_USERNAME" \
    --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1; then
    authenticated=true
    break
  fi
  sleep 2
done

if [ "$authenticated" != true ]; then
  echo "Keycloak initialization failed: administrator login was not available." >&2
  exit 1
fi

demo_user_id="$($KCADM get users -r "$REALM" -q username=pflege.demo --fields id --format csv --noquotes 2>/dev/null || true)"

# Startup realm imports deliberately skip existing realms. Partial import fills in
# missing resources without replacing existing users or organization settings.
"$KCADM" create partialImport \
  -r "$REALM" \
  -f "$IMPORT_FILE" \
  -s ifResourceExists=SKIP >/dev/null

api_client_id="$($KCADM get clients -r "$REALM" -q clientId=monitoring-pflege-api --fields id --format csv --noquotes)"
frontend_client_id="$($KCADM get clients -r "$REALM" -q clientId=monitoring-frontend --fields id --format csv --noquotes)"

if [ -z "$api_client_id" ] || [ -z "$frontend_client_id" ]; then
  echo "Keycloak initialization failed: required clients are missing." >&2
  exit 1
fi

"$KCADM" update "clients/$frontend_client_id" \
  -r "$REALM" \
  -s "secret=$OIDC_CLIENT_SECRET" \
  -s "redirectUris=[\"$OIDC_REDIRECT_URI\"]" \
  -s "webOrigins=[\"$APP_ORIGIN\"]" >/dev/null

for role in pflege_read pflege_write pflege_delete pflege_admin; do
  if ! "$KCADM" get "clients/$api_client_id/roles/$role" -r "$REALM" >/dev/null 2>&1; then
    "$KCADM" create "clients/$api_client_id/roles" -r "$REALM" -s "name=$role" >/dev/null
  fi
done

if [ -z "$demo_user_id" ]; then
  "$KCADM" set-password \
    -r "$REALM" \
    --username pflege.demo \
    --new-password "$DEMO_USER_PASSWORD" \
    --temporary >/dev/null
fi

"$KCADM" add-roles \
  -r "$REALM" \
  --uusername pflege.demo \
  --cclientid monitoring-pflege-api \
  --rolename pflege_read \
  --rolename pflege_write >/dev/null

echo "Keycloak realm configuration is ready."
