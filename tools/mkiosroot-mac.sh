#!/bin/bash
# macOS version of mkiosroot.sh: build the case-sensitive journaled HFS+ iOS root
# (OS root + SystemOS/AppOS cryptexes) for the userdata partition (rd=ufsroot0),
# then apply sweet-root-tweaks.py. Same layout and fix-ups as the Linux script.
#
#   sudo tools/mkiosroot-mac.sh OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE]   (SIZE default 16g)
#
# macOS mounts the IPSW images natively (the OS image is UDIF, the cryptexes raw
# APFS) and decompresses their files on read, so the HFS+ copy is uncompressed,
# as on Linux. OUT.img is a sparse raw volume (no partition map): only written
# blocks take disk space, and fastboot skips the empty ones when flashing.
set -euo pipefail

[[ $# -ge 4 ]] || { sed -n '2,11p' "$0"; exit 2; }
[[ $EUID == 0 ]] || { echo "run with sudo: file owners must be preserved" >&2; exit 1; }
here=$(cd "$(dirname "$0")" && pwd)
os=$(realpath "$1") sysos=$(realpath "$2") appos=$(realpath "$3") out=$4 size=${5:-16g}
[[ ! -e $out ]] || { echo "refusing to overwrite $out" >&2; exit 1; }

work=$(mktemp -d /private/tmp/iosroot.XXXXXX)
devs=()
cleanup() {
	for m in "$work"/root "$work"/os "$work"/sysos "$work"/appos; do
		mount | grep -q " on $m " && umount "$m" 2>/dev/null || true
	done
	for d in ${devs[@]+"${devs[@]}"}; do
		hdiutil detach -quiet "$d" 2>/dev/null || true
	done
	rmdir "$work"/* "$work" 2>/dev/null || true
}
trap cleanup EXIT

# Source images read-only, with real owners (macOS ignores them on images by default).
attach_ro() {
	local img=$1 name=$2 raw=$3 dev
	mkdir "$work/$name"
	local key=()
	[[ $raw == raw ]] && key=(-imagekey diskimage-class=CRawDiskImage)
	dev=$(hdiutil attach -readonly -nobrowse -owners on ${key[@]+"${key[@]}"} -mountpoint "$work/$name" "$img" | awk 'NR==1{print $1}')
	devs+=("$dev")
}
attach_ro "$os" os udif
attach_ro "$sysos" sysos raw
attach_ro "$appos" appos raw

# Target: sparse raw file -> one case-sensitive journaled HFS+ volume.
mkfile -n "$size" "$out"
tdev=$(hdiutil attach -nomount -imagekey diskimage-class=CRawDiskImage "$out" | awk 'NR==1{print $1}')
devs=("$tdev" "${devs[@]}")
newfs_hfs -s -J -v iOSRoot "$tdev"
mkdir "$work/root"
mount -t hfs "$tdev" "$work/root"
diskutil enableOwnership "$work/root" >/dev/null
# Keep Spotlight and fseventsd from writing their files into the iOS root.
touch "$work/root/.metadata_never_index"
mdutil -i off "$work/root" >/dev/null 2>&1 || true

copy() {
	echo "copying $1 -> ${2#"$work/root"}"
	mkdir -p "$2"
	rsync -aH --numeric-ids "$1/" "$2/"
}
copy "$work/os" "$work/root"
copy "$work/sysos" "$work/root/private/preboot/Cryptexes/OS"
copy "$work/appos" "$work/root/private/preboot/Cryptexes/App"

# Shared cache where dyld looks at ignition level 1: hard links, no extra space.
dsc=private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld
mkdir -p "$work/root/System/Library/Caches/com.apple.dyld"
for f in "$work/root/$dsc"/*; do
	ln "$f" "$work/root/System/Library/Caches/com.apple.dyld/${f##*/}"
done

# dyld does not search the cryptexes at ignition level 1: hard-link every cryptex
# file that has no counterpart in the OS root to its root path (symlinks copied).
for c in OS App; do
	(cd "$work/root/private/preboot/Cryptexes/$c" && find . ! -type d ! -path './System/Library/Caches/com.apple.dyld/*') |
	while IFS= read -r f; do
		f=${f#./}
		if [[ ! -e "$work/root/$f" && ! -L "$work/root/$f" ]]; then
			mkdir -p "$work/root/$(dirname "$f")"
			src="$work/root/private/preboot/Cryptexes/$c/$f"
			if [[ -L $src ]]; then cp -P "$src" "$work/root/$f"; else ln "$src" "$work/root/$f"; fi
			echo "linked $c:/$f"
		fi
	done
done

# logd's log stores, normally made at restore (owner _logd 272, .migrated markers).
db="$work/root/private/var/db"
install -d -o 272 -g 272 -m 0751 "$db/diagnostics"
install -d -o 272 -g 272 -m 0755 "$db/uuidtext" "$db/diagnostics/timesync"
for d in diagnostics uuidtext diagnostics/timesync; do
	install -o 272 -g 272 -m 0644 /dev/null "$db/$d/.migrated"
done

# System keybag for the built-in AppleKeyStore (no passcode).
install -d -m 0700 -o 0 -g 0 "$work/root/private/var/keybags"
kb=$(mktemp)
printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
	'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
	'<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>' > "$kb"
install -m 0600 -o 0 -g 0 "$kb" "$work/root/private/var/keybags/systembag.kb"
rm -f "$kb"

# The bring-up fixes that took sweet to the home screen (Setup skip, no baseband, ...).
python3 "$here/sweet-root-tweaks.py" "$work/root"

# Whatever macOS may still have dropped at the volume root.
rm -rf "$work/root/.fseventsd" "$work/root/.Spotlight-V100" "$work/root/.Trashes" "$work/root/.metadata_never_index"
df -h "$work/root"
umount "$work/root"
fsck_hfs -f -y "$tdev" || true
fsck_hfs -f -n "$tdev"
ls -lsh "$out"
