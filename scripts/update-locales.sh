#!/bin/sh
# Compile every .po into its .mo (the bundled catalogues are what the launcher and the wheel use).
# Regenerating the .pot from source: xgettext -L Python -k_ -o compartir_selector/locale/compartir-selector.pot compartir_selector/*.py
set -eu
cd "$(dirname "$0")/.."
for po in compartir_selector/locale/*/LC_MESSAGES/compartir-selector.po; do
  msgfmt --check -o "${po%.po}.mo" "$po"
  echo "compiled $po"
done
