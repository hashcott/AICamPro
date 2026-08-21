# shellcheck shell=bash
# Cây /usr dùng chung cho các gói của hệ thống: .deb, .rpm, .pkg.tar.zst.
#
# Ba định dạng đó chỉ khác nhau ở phần siêu dữ liệu (control / spec / PKGBUILD);
# phần nội dung — ứng dụng, launcher, desktop entry, icon, man — phải giống nhau
# từng byte, nếu không thì sửa đường dẫn ở một định dạng sẽ âm thầm bỏ sót hai
# định dạng còn lại. Vì thế nó nằm ở đây, không nằm trong từng script build.
#
# Cách dùng:
#   source "$(dirname "$0")/lib-systree.sh"
#   systree_build /đường/dẫn/buildroot
#
# PKGBUILD của Arch cũng source đúng file này từ trong $srcdir.

SYSTREE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTREE_PKG="aicampro"

# Đọc version từ pyproject.toml — một nguồn duy nhất cho mọi định dạng gói.
systree_version() {
    python3 -c "import tomllib; print(tomllib.load(open('$SYSTREE_ROOT/pyproject.toml','rb'))['project']['version'])"
}

# Trích phần thân của một mục CHANGELOG.md ra stdout (rỗng nếu không có mục đó).
systree_changelog_body() {  # version
    python3 - "$SYSTREE_ROOT/CHANGELOG.md" "$1" <<'PYEOF'
import re, sys
from pathlib import Path
text, version = Path(sys.argv[1]).read_text(), sys.argv[2]
m = re.search(rf"^## \[{re.escape(version)}\].*?$\n(.*?)(?=^## \[|\Z)",
              text, re.MULTILINE | re.DOTALL)
print(m.group(1).strip() if m else "")
PYEOF
}

# Dựng toàn bộ nội dung gói vào $1 (buildroot). Không ghi gì ngoài $1.
systree_build() {  # dest_root
    local dest="$1"
    local pkg="$SYSTREE_PKG"

    install -d "$dest/usr/bin" \
               "$dest/usr/lib/$pkg" \
               "$dest/usr/lib/$pkg/scripts" \
               "$dest/usr/share/applications" \
               "$dest/usr/share/icons/hicolor/scalable/apps" \
               "$dest/usr/share/doc/$pkg" \
               "$dest/usr/share/man/man1"

    echo "→ chép ứng dụng"
    cp -r "$SYSTREE_ROOT/aicampro" "$dest/usr/lib/$pkg/"
    find "$dest/usr/lib/$pkg" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    # cp giữ nguyên quyền của cây làm việc (664/775); các gói đòi 644/755
    find "$dest/usr/lib/$pkg" -type f -exec chmod 0644 {} +
    find "$dest/usr/lib/$pkg" -type d -exec chmod 0755 {} +
    install -m 0755 "$SYSTREE_ROOT/scripts/download_models.sh" "$dest/usr/lib/$pkg/scripts/"
    install -m 0755 "$SYSTREE_ROOT/scripts/setup_v4l2loopback.sh" "$dest/usr/lib/$pkg/scripts/"

    echo "→ lệnh và tích hợp desktop"
    install -m 0755 "$SYSTREE_ROOT/packaging/launcher.sh" "$dest/usr/bin/aicampro"
    install -m 0755 "$SYSTREE_ROOT/packaging/aicampro-setup" "$dest/usr/bin/aicampro-setup"
    install -m 0644 "$SYSTREE_ROOT/packaging/aicampro.desktop" "$dest/usr/share/applications/"
    local page
    for page in aicampro aicampro-setup; do
        gzip -9n -c "$SYSTREE_ROOT/packaging/man/$page.1" > "$dest/usr/share/man/man1/$page.1.gz"
        chmod 0644 "$dest/usr/share/man/man1/$page.1.gz"
    done
    install -m 0644 "$SYSTREE_ROOT/packaging/icons/aicampro.svg" \
            "$dest/usr/share/icons/hicolor/scalable/apps/aicampro.svg"
    local size
    for size in 16 24 32 48 64 128 256 512; do
        install -d "$dest/usr/share/icons/hicolor/${size}x${size}/apps"
        install -m 0644 "$SYSTREE_ROOT/packaging/icons/aicampro-${size}.png" \
                "$dest/usr/share/icons/hicolor/${size}x${size}/apps/aicampro.png"
    done

    echo "→ tài liệu"
    install -m 0644 "$SYSTREE_ROOT/README.md" "$dest/usr/share/doc/$pkg/"
    install -m 0644 "$SYSTREE_ROOT/README.vi.md" "$dest/usr/share/doc/$pkg/"
}
