#!/bin/sh
# Compile every .po into its .mo (the bundled catalogues are what the launcher and the wheel use).
# Regenerating the .pot from source: xgettext -L Python -k_ -o wlr_share_picker/locale/wlr-share-picker.pot wlr_share_picker/*.py
set -eu
cd "$(dirname "$0")/.."
for po in wlr_share_picker/locale/*/LC_MESSAGES/wlr-share-picker.po; do
  msgfmt --check -o "${po%.po}.mo" "$po"
  echo "compiled $po"
done
