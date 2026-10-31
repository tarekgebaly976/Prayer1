Files served at https://<domain>/.well-known/ (see deploy/Caddyfile).

assetlinks.json links the Android app on Google Play to this website, so the app opens it full screen without
a browser bar. It holds only the app's package name and the SHA-256 fingerprints of its signing certificates
(public values, not secrets). Get it from PWABuilder's Android package, then add the "App signing key certificate"
fingerprint shown in Play Console › Test and release › App integrity.
