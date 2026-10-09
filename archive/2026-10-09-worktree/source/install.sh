#!/usr/bin/env bash
# Установка офлайн-игры «Архив неизвестного» (фестиваль «Наука 0+») без root.
#
# Использование:
#   ./install.sh [ПУТЬ_УСТАНОВКИ]
# Путь по умолчанию: $HOME/.local/share/science-day
# Пути с пробелами поддерживаются. Интернет и права администратора не нужны.
set -euo pipefail

dest="${1:-$HOME/.local/share/science-day}"
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Копируем игру (index.html, скрипты, стили, данные, real/, docs/, LICENSES.txt).
mkdir -p "$dest"
cp -R "$src/." "$dest/"
echo "Установлено: $dest"

# 2. Ярлык — только на Linux; на macOS игра открывается напрямую.
if [ "$(uname -s)" = "Darwin" ]; then
  echo "macOS: откройте игру файлом \"$dest/index.html\" (двойной щелчок) или: open \"$dest/index.html\""
  exit 0
fi

apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$apps_dir"
launcher="$apps_dir/science-day.desktop"
cat > "$launcher" <<EOF
[Desktop Entry]
Type=Application
Name=Архив неизвестного
Comment=Охота за звёздными аномалиями — офлайн-игра «Наука 0+»
Exec=xdg-open "$dest/index.html"
Terminal=false
Categories=Science;Education;
EOF
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$apps_dir" || true
fi
echo "Ярлык создан: $launcher (пункт «Архив неизвестного» в меню приложений)."
echo "Запуск без ярлыка: xdg-open \"$dest/index.html\""
