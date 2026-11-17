#!/usr/bin/env bash
# 抖音原画解析服务：部署/升级脚本（在目标 Linux 服务器上以 root 执行）
#
# 用法：
#   sudo bash deploy/linux/deploy.sh /tmp/douyin-original-parser-deploy.tar.gz
#   sudo bash deploy/linux/deploy.sh /tmp/xxx.tar.gz --install-units --create-account
#
# 默认更新源码、启动脚本及虚拟环境依赖，保留服务器上已有的 systemd 配置，避免覆盖端口、
# 并发数等本机设置。首次部署请加 --install-units 和 --create-account。

set -uo pipefail

TARGET="/opt/software/python"
SERVICE="douyin-original-parser"
SERVICE_USER="douyin-parser"
SERVICE_HOME="/home/douyin-parser"
PACKAGE=""
INSTALL_UNITS=0
CREATE_ACCOUNT=0

usage() {
  cat <<'USAGE'
用法：sudo bash deploy.sh <部署包.tar.gz> [选项]

选项：
  --target <目录>      项目目录，默认 /opt/software/python
  --install-units      安装 systemd 服务单元与请求保护配置（首次部署需要）
  --create-account     创建服务账户与可写家目录（首次部署需要）
  -h, --help           显示本帮助

不带参数时会自动在 /tmp、当前目录、项目目录下查找 douyin-original-parser-deploy*.tar.gz。
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target)
      [ $# -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] \
        || { echo "错误：--target 需要目录参数。" >&2; exit 2; }
      TARGET="$2"; shift 2 ;;
    --install-units) INSTALL_UNITS=1; shift ;;
    --create-account) CREATE_ACCOUNT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "未知选项：$1" >&2; usage >&2; exit 2 ;;
    *) PACKAGE="$1"; shift ;;
  esac
done

fail() { echo "错误：$*" >&2; exit 1; }
step() { echo; echo "== $* =="; }

[ "$(id -u)" = "0" ] || fail "需要 root 权限，请使用 sudo 执行。"

if [ -z "$PACKAGE" ]; then
  for dir in /tmp "$PWD" "$TARGET"; do
    for candidate in "$dir"/douyin-original-parser-deploy*.tar.gz; do
      [ -f "$candidate" ] && PACKAGE="$candidate"
    done
    [ -n "$PACKAGE" ] && break
  done
fi
[ -n "$PACKAGE" ] || fail "没有找到部署包，请作为第一个参数指定 .tar.gz 路径。"
[ -f "$PACKAGE" ] || fail "部署包不存在：$PACKAGE"
[ -d "$TARGET" ] || fail "项目目录不存在：$TARGET（首次部署请先解压部署包）"

step "校验部署包：$PACKAGE"
tar -tzf "$PACKAGE" >/dev/null 2>&1 || fail "部署包无法读取或已损坏。"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$(mktemp -d)"
BACKUP="/tmp/douyin-backup-$TIMESTAMP.tar.gz"
trap 'rm -rf "$STAGE"' EXIT
tar -xzf "$PACKAGE" -C "$STAGE" --strip-components=1 || fail "解压部署包失败。"
[ -f "$STAGE/run.py" ] || fail "部署包结构异常：缺少 run.py。"
[ -f "$STAGE/original_parser/guard.py" ] || fail "部署包结构异常：缺少 original_parser/guard.py。"

# 安装时若主单元已存在，先备份，失败后自动还原，避免服务单元被新配置破坏。
UNITS_CHANGED=0
install() {
  local source="$1" destination="$2"
  if [ -f "$destination" ]; then
    cp -p "$destination" "$destination.bak-$TIMESTAMP"
    UNITS_CHANGED=1
  fi
  /usr/bin/install -m "${3:-644}" "$source" "$destination"
}

copy_tree() {
  local source="$1" destination="$2"
  mkdir -p "$destination"
  cp -a "$source/." "$destination/"
}

restore_units() {
  [ "$UNITS_CHANGED" = "1" ] || return 0
  echo "正在还原 systemd 配置……" >&2
  if [ -f "/etc/systemd/system/$SERVICE.service.bak-$TIMESTAMP" ]; then
    mv -f "/etc/systemd/system/$SERVICE.service.bak-$TIMESTAMP" "/etc/systemd/system/$SERVICE.service"
  fi
  local dropin="/etc/systemd/system/$SERVICE.service.d/90-request-protection.conf"
  if [ -f "$dropin.bak-$TIMESTAMP" ]; then
    mv -f "$dropin.bak-$TIMESTAMP" "$dropin"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
}

[ "$CREATE_ACCOUNT" = "1" ] && {
  step "创建服务账户与可写家目录"
  id "$SERVICE_USER" >/dev/null 2>&1 \
    || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" \
    || fail "创建服务账户失败。"
  # 目录不存在或属主不对时 Chromium 的 crashpad 会初始化失败，服务会一直返回 502。
  /usr/bin/install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_USER" "$SERVICE_HOME" || fail "创建家目录失败。"
  echo "已确认账户 $SERVICE_USER 与可写家目录 $SERVICE_HOME。"
}

step "备份当前源码到 $BACKUP"
BACKUP_TARGETS=()
for item in original_parser run.py parse_links.py requirements.txt package.py original_metadata.json; do
  [ -e "$TARGET/$item" ] && BACKUP_TARGETS+=("$item")
done
[ -f "$TARGET/README.md" ] && BACKUP_TARGETS+=("README.md")
[ -d "$TARGET/deploy" ] && BACKUP_TARGETS+=("deploy")
if [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
  tar -czf "$BACKUP" -C "$TARGET" "${BACKUP_TARGETS[@]}" || fail "备份失败。"
  echo "备份完成：$BACKUP（回退：tar -xzf $BACKUP -C $TARGET）"
else
  echo "目标目录还没有可备份的内容，按首次部署继续。"
fi

step "停止服务"
if systemctl list-unit-files "$SERVICE.service" >/dev/null 2>&1 \
   && systemctl cat "$SERVICE" >/dev/null 2>&1; then
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  echo "已停止 $SERVICE。"
else
  echo "服务单元尚未安装，跳过停止。"
fi

step "覆盖源码"
copy_tree "$STAGE/original_parser" "$TARGET/original_parser"
copy_tree "$STAGE/deploy" "$TARGET/deploy"
cp -f "$STAGE/run.py" "$TARGET/run.py"
for item in parse_links.py requirements.txt package.py README.md original_metadata.json; do
  [ -f "$STAGE/$item" ] && cp -f "$STAGE/$item" "$TARGET/$item"
done
chmod -R a+rX "$TARGET"
echo "已更新：$(cd "$TARGET" && ls original_parser/*.py | wc -l) 个源码文件、deploy 目录与入口脚本。"

step "同步服务虚拟环境依赖并检查签名功能"
[ -x "$TARGET/.venv/bin/python" ] || fail "缺少服务虚拟环境，请先执行 bash $TARGET/deploy/linux/install.sh。服务尚未启动。"
"$TARGET/.venv/bin/python" -m pip install -r "$TARGET/requirements.txt" \
  || fail "依赖安装失败，服务尚未启动；修复安装错误后重新执行升级。"
"$TARGET/.venv/bin/python" -m pip check \
  || fail "虚拟环境依赖冲突，服务尚未启动。"
(cd "$TARGET" && "$TARGET/.venv/bin/python" -m original_parser.check_runtime) \
  || fail "运行环境检查失败，服务尚未启动。"
# requirements 更新 Playwright 时可能需要新的 Chromium 修订；已有匹配版本则不下载。
export PLAYWRIGHT_BROWSERS_PATH="$TARGET/.browsers"
if ! "$TARGET/.venv/bin/python" -c 'from pathlib import Path; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); ready = Path(p.chromium.executable_path).is_file(); p.stop(); raise SystemExit(0 if ready else 1)'; then
  "$TARGET/.venv/bin/python" -m playwright install --with-deps chromium --no-shell \
    || fail "Chromium 安装失败，服务尚未启动。"
fi
chmod -R a+rX "$TARGET/.browsers" || fail "无法设置 Chromium 读取权限。"

if [ "$INSTALL_UNITS" = "1" ]; then
  step "安装 systemd 服务单元与请求保护配置"
  install "$TARGET/deploy/linux/$SERVICE.service" "/etc/systemd/system/$SERVICE.service"
  mkdir -p "/etc/systemd/system/$SERVICE.service.d"
  install "$TARGET/deploy/linux/request-protection.conf" \
          "/etc/systemd/system/$SERVICE.service.d/90-request-protection.conf"
  systemctl daemon-reload || { restore_units; fail "daemon-reload 失败，已还原原配置。"; }
fi

step "启动服务"
if systemctl cat "$SERVICE" >/dev/null 2>&1; then
  systemctl restart "$SERVICE" || { restore_units; fail "服务启动失败。"; }
  sleep 3
  systemctl is-active --quiet "$SERVICE" || {
    restore_units
    journalctl -u "$SERVICE" -n 40 --no-pager
    fail "服务未处于运行状态，已还原 systemd 配置，日志见上。"
  }
  echo "$SERVICE 正在运行。"
else
  echo "服务单元尚未安装（首次部署请加 --install-units），已完成文件更新。"
  exit 0
fi

step "确认请求保护参数"
if journalctl -u "$SERVICE" -n 60 --no-pager 2>/dev/null | grep -q 'protection interval'; then
  journalctl -u "$SERVICE" -n 60 --no-pager | grep 'protection interval' | tail -1
else
  echo "未在最近日志中找到 protection interval，请执行：journalctl -u $SERVICE -n 60 --no-pager"
fi

step "健康检查"
if curl --noproxy '*' --fail --silent --show-error "http://127.0.0.1:8765/health" >/dev/null; then
  echo "本机 /health 正常。"
else
  echo "本机 /health 未通过，请检查日志：journalctl -u $SERVICE -n 60 --no-pager"
fi

echo
echo "完成。回退命令：systemctl stop $SERVICE && tar -xzf $BACKUP -C $TARGET && systemctl start $SERVICE"
