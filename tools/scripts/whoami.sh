#!/usr/bin/env bash
# whoami.sh — 根据 IP 地址识别当前用户
# 用法: bash whoami.sh <项目根目录路径>

BASE_DIR="${1:-.}"
MAPPING_FILE="${BASE_DIR}/records/ip-mapping.md"

# 获取本机 IP（192.168 网段）
IP=$(ipconfig 2>/dev/null | grep -m1 "IPv4" | sed 's/.*: *//')
HOSTNAME_RAW=$(hostname 2>/dev/null || echo "unknown")

if [ -z "$IP" ]; then
    echo "UNKNOWN"
    exit 1
fi

# 在映射表中查找用户身份
if [ -f "$MAPPING_FILE" ]; then
    # 优先用主机名匹配（DHCP 会让 IP 漂移，主机名更稳定）
    if [ -n "$HOSTNAME_RAW" ]; then
        NAME_BY_HOST=$(awk -F'|' -v host="$HOSTNAME_RAW" '
            function trim(s) {
                gsub(/^[ \t]+|[ \t]+$/, "", s)
                return s
            }
            BEGIN { host_lc = tolower(host) }
            NF >= 4 {
                mapped_host = trim($3)
                name = trim($4)
                if (mapped_host != "" && mapped_host != "(待补充)" && tolower(mapped_host) == host_lc && name != "") {
                    names[name] = 1
                }
            }
            END {
                for (name in names) {
                    count++
                    only_name = name
                }
                if (count == 1) {
                    print only_name
                }
            }
        ' "$MAPPING_FILE")

        if [ -n "$NAME_BY_HOST" ]; then
            echo "$NAME_BY_HOST"
            exit 0
        fi
    fi

    # 主机名未命中时，再按 IP 匹配
    MATCHED=$(grep "$IP" "$MAPPING_FILE" | head -1)
    if [ -n "$MATCHED" ]; then
        NAME=$(echo "$MATCHED" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $4); print $4}')
        if [ -n "$NAME" ]; then
            echo "$NAME"
            exit 0
        fi
    fi
fi

echo "UNKNOWN|$IP"
