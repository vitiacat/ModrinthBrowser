#!/bin/bash
for filename in *.ts; do
  lrelease "$filename" -qm "../${filename%.*}.qm"
done