#!/bin/bash

if [[ "$PWD" != */spot ]]; then
  cd spot || exit 1
fi

SPOT_TAR=$(ls spot-*.tar.gz | head -n 1)
tar --extract --file="$SPOT_TAR" --gzip --verbose;
cd "${SPOT_TAR%.tar.gz}";
./configure --disable-devel;
sudo make install;

cd ..
# Move all files (including hidden ones) to the current directory
mv "${SPOT_TAR%.tar.gz}"/* . 2>/dev/null
mv "${SPOT_TAR%.tar.gz}"/.[!.]* . 2>/dev/null 

# Remove the now-empty directory
rmdir "${SPOT_TAR%.tar.gz}"
