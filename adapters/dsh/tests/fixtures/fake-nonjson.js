// Fake vision-translation CLI: exits nonzero with junk on stdout (no valid
// JSON) and a diagnostic on stderr — exercises B9.
process.stdout.write("this is not json {");
process.stderr.write("[fake-cli] internal boom: disk full, whatever\n");
process.exitCode = 1;
