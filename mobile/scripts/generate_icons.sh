#!/bin/bash
set -e

# Generate TheHopper app icons from SVG source
# Requires: rsvg-convert (or imagemagick) and pngquant
# If not available, uses Python with cairosvg

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/../assets/app-icon.svg"
ICON_DIR="$SCRIPT_DIR/../assets/icons"

mkdir -p "$ICON_DIR"

# Check for rsvg-convert
if command -v rsvg-convert &>/dev/null; then
    CONVERT="rsvg-convert"
    CONVERT_CMD=(rsvg-convert -w)
elif command -v convert &>/dev/null; then
    CONVERT="convert"
    CONVERT_CMD=(convert -background none)
else
    echo "Neither rsvg-convert nor ImageMagick found. Using Python cairosvg..."
    pip install cairosvg 2>/dev/null || pip3 install cairosvg 2>/dev/null
    python3 -c "
import cairosvg, os
sizes = {
    'icon-1024.png': 1024,
    'icon-180.png': 180,
    'icon-167.png': 167,
    'icon-152.png': 152,
    'icon-120.png': 120,
    'icon-87.png': 87,
    'icon-80.png': 80,
    'icon-76.png': 76,
    'icon-60.png': 60,
    'icon-40.png': 40,
    'icon-29.png': 29,
    'icon-20.png': 20,
    'playstore-icon.png': 512,
    'adaptive-icon.png': 432,
    'favicon.png': 48,
}
for name, size in sizes.items():
    out = os.path.join('$ICON_DIR', name)
    cairosvg.svg2png(url='$SOURCE', write_to=out, output_width=size, output_height=size)
    print(f'  Generated {name} ({size}x{size})')
print('Done!')
"
    exit 0
fi

# iOS icons
for size_name in "1024:icon-1024.png" "180:icon-180.png" "167:icon-167.png" "152:icon-152.png" "120:icon-120.png" "87:icon-87.png" "80:icon-80.png" "76:icon-76.png" "60:icon-60.png" "40:icon-40.png" "29:icon-29.png" "20:icon-20.png"; do
    size="${size_name%%:*}"
    name="${size_name##*:}"
    if [ "$CONVERT" = "rsvg-convert" ]; then
        rsvg-convert -w "$size" -h "$size" "$SOURCE" -o "$ICON_DIR/$name"
    else
        convert -background none -resize "${size}x${size}" "$SOURCE" "$ICON_DIR/$name"
    fi
    echo "  Generated $name (${size}x${size})"
done

# Android / Play Store icons
for size_name in "512:playstore-icon.png" "432:adaptive-icon.png" "48:favicon.png"; do
    size="${size_name%%:*}"
    name="${size_name##*:}"
    if [ "$CONVERT" = "rsvg-convert" ]; then
        rsvg-convert -w "$size" -h "$size" "$SOURCE" -o "$ICON_DIR/$name"
    else
        convert -background none -resize "${size}x${size}" "$SOURCE" "$ICON_DIR/$name"
    fi
    echo "  Generated $name (${size}x${size})"
done

echo "✓ All icons generated in $ICON_DIR"
