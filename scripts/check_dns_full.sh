#!/bin/bash
echo "=== Authoritative (REG.RU) ==="
dig +short admin.qooqvpn.ru @ns1.reg.ru
dig +short app.qooqvpn.ru @ns1.reg.ru
dig +short keys.qooqvpn.ru @ns1.reg.ru
echo ""
echo "=== Google DNS ==="
dig +short admin.qooqvpn.ru @8.8.8.8
dig +short app.qooqvpn.ru @8.8.8.8
echo ""
echo "=== Normal lookup (recursive) ==="
host -t A admin.qooqvpn.ru
host -t A app.qooqvpn.ru
echo ""
echo "=== With norecurse (like user test - often REFUSED) ==="
dig +norecurse admin.qooqvpn.ru @127.0.0.53 2>&1 | tail -3
echo ""
echo "=== All records in zone ==="
dig @ns1.reg.ru qooqvpn.ru ANY +noall +answer 2>/dev/null | head -30
