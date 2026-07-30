# Bloom Ops monitor

Monitor complementar executado no host da VPS a cada cinco minutos.

## Sinais monitorados

- disco raiz: alerta a partir de 75%;
- memória: alerta a partir de 85%;
- swap: alerta a partir de 90%;
- `/tmp`: alerta a partir de 1 GiB;
- presença de diretórios `/tmp/tirith-install-*`;
- saúde e reinícios do Hermes Agent e WebUI;
- estado do gateway `gateway-bloom` no s6;
- disponibilidade da consulta aos crons Bloom e indicação textual de falhas.

Alertas são deduplicados. Uma nova mensagem é enviada quando um problema surge,
muda ou é recuperado.

## Arquivos instalados

- `/usr/local/sbin/bloom-ops-monitor`
- `/etc/systemd/system/bloom-ops-monitor.service`
- `/etc/systemd/system/bloom-ops-monitor.timer`
- `/etc/bloom-ops/telegram.env` (`root:root`, modo `0600`)
- `/var/lib/bloom-ops/state.json`

## Operação

```bash
systemctl status bloom-ops-monitor.timer
systemctl start bloom-ops-monitor.service
journalctl -u bloom-ops-monitor.service
cat /var/lib/bloom-ops/state.json
```

O cron editorial ainda não existe. Quando ele for criado, a verificação deve ser
ampliada para considerar o horário esperado e o resultado estruturado de cada
execução.
