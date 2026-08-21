#!/usr/bin/env bash
# Dựng gói .rpm (Fedora, openSUSE, RHEL) cho AICamPro.
#
# Gói là noarch vì toàn bộ mã là Python thuần; phần nhị phân nặng (PyTorch
# ROCm, Qt, OpenCV) do aicampro-setup tải về môi trường người dùng.
#
# Nội dung cây /usr do lib-systree.sh dựng, dùng chung với .deb và Arch: spec ở
# đây chỉ khai báo, không tự chép file, nên ba định dạng không thể lệch nhau.
#
# Cần rpmbuild. Trên máy không có: chạy trong container Fedora —
#   docker run --rm -v "$PWD:/src" -w /src fedora:latest \
#       sh -c 'dnf -y install rpm-build python3 && ./packaging/build-rpm.sh'
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=packaging/lib-systree.sh
source "$ROOT/packaging/lib-systree.sh"

OUT="${OUT_DIR:-$ROOT/dist}"
VERSION="$(systree_version)"
PKG="aicampro"
RELEASE="${RPM_RELEASE:-1}"

command -v rpmbuild >/dev/null || {
    echo "✗ không có rpmbuild (Fedora: dnf install rpm-build; Debian: apt install rpm)" >&2
    exit 1
}

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

SYSTREE="$BUILD/SOURCES/systree"
install -d "$SYSTREE" "$BUILD/SPECS" "$BUILD/RPMS"
systree_build "$SYSTREE"
install -m 0644 "$ROOT/LICENSE" "$SYSTREE/usr/share/doc/$PKG/LICENSE"

# rpm đòi %changelog theo định dạng riêng: một dòng header rồi các gạch đầu
# dòng. Lấy đúng mục của phiên bản này trong CHANGELOG.md.
CHANGELOG="$BUILD/changelog.txt"
{
    printf '* %s Harry Nguyen <duchanhstyle@gmail.com> - %s-%s\n' \
        "$(LC_ALL=C date '+%a %b %d %Y')" "$VERSION" "$RELEASE"
    body="$(systree_changelog_body "$VERSION")"
    if [[ -n "$body" ]]; then
        printf '%s\n' "$body" | sed -n 's/^- /- /p'
    else
        printf -- '- See CHANGELOG.md for the %s entry.\n' "$VERSION"
    fi
} > "$CHANGELOG"

SPEC="$BUILD/SPECS/$PKG.spec"
cat > "$SPEC" <<SPEC
Name:           $PKG
Version:        $VERSION
Release:        ${RELEASE}%{?dist}
Summary:        AI webcam with background removal, accelerated on AMD GPUs
License:        MIT
URL:            https://github.com/hashcott/AICamPro
BuildArch:      noarch

Requires:       python3 >= 3.10
Requires:       python3-pip
Requires:       ca-certificates
Requires:       curl
Requires:       hicolor-icon-theme
Recommends:     ffmpeg
Recommends:     zenity

%description
AICamPro removes, blurs or replaces your webcam background, grades colour,
retouches and auto-frames you, then offers the result to Meet, Zoom, Discord
or OBS as a virtual camera. Every per-frame operation runs on the GPU through
PyTorch on ROCm.

This package contains the application only. The GPU runtime — PyTorch built
for ROCm — is around 14 GB installed and has to match the amdgpu driver on the
machine, so it is fetched into a per-user environment by running
aicampro-setup once after installation.

# Cây /usr đã được lib-systree.sh dựng sẵn ở ngoài rpmbuild; %install chỉ chép
# nguyên khối vào buildroot để một nguồn duy nhất quyết định nội dung gói.
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a %{_sourcedir}/systree/. %{buildroot}/

%post
cat <<'MSG'

AICamPro đã cài. Chạy một lần để tải môi trường GPU và model:

    aicampro-setup

Muốn dùng webcam ảo trong Meet/Zoom/OBS thì chạy thêm:

    sudo /usr/lib/aicampro/scripts/setup_v4l2loopback.sh

MSG

%files
# Tài liệu đi qua _datadir/doc chứ không qua macro _docdir: trên openSUSE macro
# đó trỏ tới /usr/share/doc/packages, không khớp cây mà lib-systree.sh đã dựng.
# (Comment trong spec không được chứa macro dạng ngoặc — rpmbuild vẫn nở nó ra.)
%license %{_datadir}/doc/%{name}/LICENSE
%doc %{_datadir}/doc/%{name}/README.md
%doc %{_datadir}/doc/%{name}/README.vi.md
%{_bindir}/aicampro
%{_bindir}/aicampro-setup
%{_prefix}/lib/%{name}/
%{_datadir}/applications/aicampro.desktop
%{_datadir}/icons/hicolor/*/apps/aicampro.svg
%{_datadir}/icons/hicolor/*/apps/aicampro.png
%{_mandir}/man1/aicampro.1.gz
%{_mandir}/man1/aicampro-setup.1.gz

%changelog
$(cat "$CHANGELOG")
SPEC

echo "→ rpmbuild"
rpmbuild -bb \
    --define "_topdir $BUILD" \
    --define "_rpmdir $BUILD/RPMS" \
    --buildroot "$BUILD/buildroot" \
    "$SPEC" 2>&1 | sed -n '/^Wrote:/p;/^error/p;/warning:/p'

mkdir -p "$OUT"
RPM="$(find "$BUILD/RPMS" -name '*.rpm' -type f | head -1)"
[[ -n "$RPM" ]] || { echo "✗ rpmbuild không tạo ra gói nào" >&2; exit 1; }
install -m 0644 "$RPM" "$OUT/"
echo "✓ $OUT/$(basename "$RPM") ($(du -h "$RPM" | cut -f1))"

if command -v rpmlint >/dev/null 2>&1; then
    echo "→ rpmlint"
    rpmlint "$OUT/$(basename "$RPM")" || true
fi
