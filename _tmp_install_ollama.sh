set -e
id ollama >/dev/null 2>&1 || useradd -r -m -d /var/lib/ollama -s /usr/sbin/nologin ollama

echo "[1/4] 解压到 /usr/local ..."
tar -xzf /home/pi/ollama.tgz -C /usr/local
chown -R root:root /usr/local/bin/ollama /usr/local/lib/ollama 2>/dev/null || true
/usr/local/bin/ollama --version

echo "[2/4] 写 systemd 服务 ..."
cat > /etc/systemd/system/ollama.service <<'UNIT'
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
Type=simple
User=ollama
Group=ollama
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"

[Install]
WantedBy=multi-user.target
UNIT

echo "[3/4] 启动并设置开机自启 ..."
systemctl daemon-reload
systemctl enable --now ollama
sleep 3
systemctl is-active ollama

echo "[4/4] API 检查 ..."
curl -s -o /dev/null -w 'tags_api=%{http_code}\n' http://127.0.0.1:11434/api/tags
rm -f /home/pi/ollama.tgz
