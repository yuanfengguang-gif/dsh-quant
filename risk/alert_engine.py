# -*- coding: utf-8 -*-
"""risk/alert_engine.py —— 预警引擎（层8 监控预警层）

5 类预警：回撤 / 因子失效 / 执行异常 / 数据异常 / 择时防御期。
通知通道（config/alerts.yaml notify 段）：Server酱(微信) / 企业微信机器人 / 邮件；
全部未配置时降级为「控制台 + logs/alerts.log」。

用法：
  from risk.alert_engine import AlertEngine
  eng = AlertEngine()
  alerts = eng.check(current_drawdown=-0.12, factor_icirs={"amihud": 0.05, "kdj_j": -0.11},
                     exec_buy_fail=2, data_health=75.0, regime="bear")
  eng.notify(alerts)
"""
import json
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
LOG = BASE / "logs" / "alerts.log"

# 预警级别：info / warn / critical
LEVEL_ORDER = {"info": 0, "warn": 1, "critical": 2}


@dataclass
class Alert:
    type: str            # drawdown / factor / exec / data / regime
    level: str           # info / warn / critical
    message: str


class AlertEngine:
    def __init__(self, config: dict = None):
        cfg = config or self._load_config()
        a = cfg.get("alerts", {})
        self.dd_warn = a.get("drawdown_warning", 0.05)
        self.dd_ctrl = a.get("drawdown_control", 0.10)
        self.dd_circuit = a.get("drawdown_circuit", 0.15)
        self.icir_window = a.get("factor_icir_window", 20)
        self.icir_fail = a.get("factor_icir_fail", 0.0)
        self.fail_days = a.get("factor_fail_days", 20)
        self.exec_fail_max = a.get("exec_fail_max", 3)
        self.data_health_min = a.get("data_health_min", 80.0)
        self.n = cfg.get("notify", {})

    @staticmethod
    def _load_config():
        try:
            import yaml
            p = BASE / "config" / "alerts.yaml"
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    # ---------- 5 类预警检查 ----------
    def check_drawdown(self, current_drawdown):
        """current_drawdown: 负值（-0.12 = 回撤 12%）。"""
        if current_drawdown is None:
            return []
        if current_drawdown <= -self.dd_circuit:
            return [Alert("drawdown", "critical", f"回撤 {current_drawdown:.1%} ≥ 熔断线 {self.dd_circuit:.0%}")]
        if current_drawdown <= -self.dd_ctrl:
            return [Alert("drawdown", "warn", f"回撤 {current_drawdown:.1%} ≥ 控制线 {self.dd_ctrl:.0%}")]
        if current_drawdown <= -self.dd_warn:
            return [Alert("drawdown", "info", f"回撤 {current_drawdown:.1%} ≥ 警戒线 {self.dd_warn:.0%}")]
        return []

    def check_factor(self, factor_icirs):
        """factor_icirs: {因子名: 滚动ICIR}。转负的报失效。"""
        out = []
        for name, icir in (factor_icirs or {}).items():
            if icir is not None and icir < self.icir_fail:
                out.append(Alert("factor", "warn", f"因子 {name} 滚动{self.icir_window}日ICIR={icir:+.3f} 转负（失效）"))
        return out

    def check_exec(self, exec_buy_fail):
        """exec_buy_fail: 当期买不进(一字板)股票数。"""
        if exec_buy_fail is not None and exec_buy_fail > self.exec_fail_max:
            return [Alert("exec", "warn", f"执行异常：当期 {exec_buy_fail} 只买不进（一字板），超阈值 {self.exec_fail_max}")]
        return []

    def check_data(self, data_health):
        """data_health: data_audit 健康度(0-100)。"""
        if data_health is not None and data_health < self.data_health_min:
            return [Alert("data", "critical", f"数据异常：健康度 {data_health:.0f} < {self.data_health_min:.0f}，数据不可信")]
        return []

    def check_regime(self, regime_state):
        """regime_state: 'bull'/'bear'。空头 = 防御期提醒。"""
        if regime_state == "bear":
            return [Alert("regime", "info", "择时防御期：空头态，仓位已减半")]
        return []

    def check(self, current_drawdown=None, factor_icirs=None, exec_buy_fail=None,
              data_health=None, regime_state=None):
        """汇总 5 类预警，返回 Alert 列表。"""
        alerts = []
        alerts += self.check_drawdown(current_drawdown)
        alerts += self.check_factor(factor_icirs)
        alerts += self.check_exec(exec_buy_fail)
        alerts += self.check_data(data_health)
        alerts += self.check_regime(regime_state)
        return alerts

    # ---------- 通知 ----------
    def notify(self, alerts):
        """发送通知。无任何通道配置则降级写日志 + 控制台。返回发送结果。"""
        if not alerts:
            return {"sent": False, "note": "无预警"}
        title = self._title(alerts)
        body = self._body(alerts)
        results = {}
        # Server酱
        if self.n.get("serverchan_sendkey"):
            results["serverchan"] = self._send_serverchan(title, body)
        # 企业微信
        if self.n.get("wechat_work_webhook"):
            results["wechat_work"] = self._send_wechat_work(body)
        # 邮件
        if self.n.get("email_to") and self.n.get("email_from"):
            results["email"] = self._send_email(title, body)
        # 降级：日志 + 控制台（始终写，保证有记录）
        self._log(title, body)
        if not results:
            return {"sent": False, "note": "无通知通道配置，已降级写 logs/alerts.log"}
        return {"sent": True, "channels": results}

    @staticmethod
    def _title(alerts):
        worst = max(alerts, key=lambda a: LEVEL_ORDER.get(a.level, 0))
        return f"[DSHQuant预警] {worst.type}·{worst.level}（{len(alerts)} 条）"

    @staticmethod
    def _body(alerts):
        lines = [f"[{a.level}] {a.type}: {a.message}" for a in alerts]
        return "\n".join(lines)

    def _send_serverchan(self, title, body):
        url = f"https://sctapi.ftqq.com/{self.n['serverchan_sendkey']}.send?" + urllib.parse.urlencode(
            {"title": title, "desp": body})
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def _send_wechat_work(self, body):
        payload = json.dumps({"msgtype": "text", "text": {"content": body}}).encode("utf-8")
        req = urllib.request.Request(self.n["wechat_work_webhook"], data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def _send_email(self, title, body):
        try:
            host, port = self.n.get("email_smtp_host"), int(self.n.get("email_smtp_port", 465))
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = title
            msg["From"] = self.n["email_from"]
            msg["To"] = self.n["email_to"]
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(self.n["email_from"], self.n.get("email_password", ""))
                s.send_message(msg)
            return {"ok": True}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def _log(self, title, body):
        try:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {title}\n{body}\n"
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
        print(f"\n{'='*60}\n{title}\n{body}\n{'='*60}", flush=True)


if __name__ == "__main__":
    eng = AlertEngine()
    alerts = eng.check(current_drawdown=-0.12,
                       factor_icirs={"amihud": 0.05, "kdj_j": -0.118, "f_score": -0.117},
                       exec_buy_fail=4, data_health=75.0, regime_state="bear")
    for a in alerts:
        print(f"[{a.level}] {a.type}: {a.message}")
    eng.notify(alerts)
