#!/usr/bin/env bash
# 抖音原画解析服务：一条命令完成升级。
#
# 不依赖服务器上已有的 deploy.sh，也不用手动解压部署包：
# 从部署包里取出新代码覆盖到项目目录，需要时同时更新 systemd 单元文件。
#
# 用法：
#   sudo bash upgrade.sh                          # 自动找 banben/ 下最新的部署包
#   sudo bash upgrade.sh /path/to/包.tar.gz        # 指定部署包
#   sudo bash upgrade.sh --create-account          # 首次部署：创建服务账户与可写家目录
#   sudo bash upgrade.sh --no-units                # 只更新源码，不动 systemd 单元

set -uo pipefail

TARGET="/opt/software/python"
SEARCH_DIR="banben"
SERVICE="douyin-original-parser"
SERVICE_USER="douyin-parser"
SERVICE_HOME="/home/douyin-parser"
PORT="8765"
PACKAGE=""
INSTALL_UNITS=1
CREATE_ACCOUNT=0

usage() {
  cat <<'USAGE'
用法：sudo bash upgrade.sh [部署包.tar.gz] [选项]

选项：
  --package <文件>     部署包路径；省略时自动查找
  --dir <目录>         自动查找部署包的目录，默认 /opt/software/python/banben
  --target <目录>      项目目录，默认 /opt/software/python
  --create-account     首次部署：创建服务账户与可写家目录
  --no-units           不更新 systemd 单元文件（只更新源码）
  -h, --help           显示本帮助
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --package) PACKAGE="${2:-}"; shift 2 ;;
    --dir) SEARCH_DIR="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --create-account) CREATE_ACCOUNT=1; shift ;;
    --no-units) INSTALL_UNITS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "未知选项：$1" >&2; usage >&2; exit 2 ;;
    *) PACKAGE="$1"; shift ;;
  esac
done

fail() { echo "错误：$*" >&2; exit 1; }
step() { echo; echo "== $* =="; }

[ "$(id -u)" = "0" ] || fail "需要 root 权限，请使用 sudo 执行。"
[ -d "$TARGET" ] || fail "项目目录不存在：$TARGET"

if [ -z "$PACKAGE" ]; then
  step "在 $TARGET/$SEARCH_DIR 下查找最新部署包"
  # 不用 find：容器镜像里的基础工具不一定齐全。
  for candidate in "$TARGET/$SEARCH_DIR"/douyin-original-parser-deploy*.tar.gz; do
    [ -f "$candidate" ] || continue
    if [ -z "$PACKAGE" ] || [ "$candidate" -nt "$PACKAGE" ]; then
      PACKAGE="$candidate"
    fi
  done
  [ -n "$PACKAGE" ] || fail "没有找到部署包。请把包放到 $TARGET/$SEARCH_DIR/，或用 --package 指定路径。"
fi

[ -f "$PACKAGE" ] || fail "部署包不存在：$PACKAGE"
step "使用部署包：$PACKAGE"
tar -tzf "$PACKAGE" >/dev/null 2>&1 || fail "部署包无法读取或已损坏。"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$(mktemp -d)"
BACKUP="/tmp/douyin-backup-$TIMESTAMP.tar.gz"
trap 'rm -rf "$STAGE"' EXIT
tar -xzf "$PACKAGE" -C "$STAGE" --strip-components=1 || fail "解压部署包失败。"
[ -f "$STAGE/run.py" ] || fail "部署包结构异常：缺少 run.py。"
[ -f "$STAGE/original_parser/guard.py" ] || fail "部署包结构异常：缺少 original_parser/guard.py。"

UNITS_CHANGED=0
install_file() {
  local source="$1" destination="$2"
  if [ -f "$destination" ]; then
    cp -p "$destination" "$destination.bak-$TIMESTAMP"
    UNITS_CHANGED=1
  fi
  /usr/bin/install -m 644 "$source" "$destination"
}

restore_units() {
  [ "$UNITS_CHANGED" = "1" ] || return 0
  echo "正在还原 systemd 配置……" >&2
  for file in "/etc/systemd/system/$SERVICE.service" \
              "/etc/systemd/system/$SERVICE.service.d/90-request-protection.conf"; do
    [ -f "$file.bak-$TIMESTAMP" ] && mv -f "$file.bak-$TIMESTAMP" "$file"
  done
  systemctl daemon-reload >/dev/null 2>&1 || true
}

if [ "$CREATE_ACCOUNT" = "1" ]; then
  step "创建服务账户与可写家目录"
  id "$SERVICE_USER" >/dev/null 2>&1 \
    || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" \
    || fail "创建服务账户失败。"
  # 家目录不存在或属主不对时 Chromium 的 crashpad 会初始化失败，服务会一直返回 502。
  install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_USER" "$SERVICE_HOME" || fail "创建家目录失败。"
  echo "已确认账户 $SERVICE_USER 与可写家目录 $SERVICE_HOME。"
fi

step "备份当前源码到 $BACKUP"
BACKUP_TARGETS=()
for item in original_parser run.py parse_links.py requirements.txt package.py README.md original_metadata.json; do
  if [ -e "$TARGET/$item" ]; then
    BACKUP_TARGETS+=("$item")
  fi
done
[ -d "$TARGET/deploy" ] && BACKUP_TARGETS+=("deploy")
if [ ${#BACKUP_TARGETS[@]} -gt 0 ]; then
  tar -czf "$BACKUP" -C "$TARGET" "${BACKUP_TARGETS[@]}" || fail "备份失败。"
  echo "备份完成：$BACKUP"
  echo "回退命令：systemctl stop $SERVICE && tar -xzf $BACKUP -C $TARGET && systemctl start $SERVICE"
fi

step "停止服务"
if systemctl cat "$SERVICE" >/dev/null 2>&1; then
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  echo "已停止 $SERVICE。"
else
  echo "服务单元尚未安装，跳过停止。"
fi

step "覆盖源码"
mkdir -p "$TARGET/original_parser" "$TARGET/deploy"
cp -a "$STAGE/original_parser/." "$TARGET/original_parser/"
cp -a "$STAGE/deploy/." "$TARGET/deploy/"
for item in run.py parse_links.py requirements.txt package.py README.md original_metadata.json; do
  [ -f "$STAGE/$item" ] && cp -f "$STAGE/$item" "$TARGET/$item"
done
chmod -R a+rX "$TARGET"
echo "已更新源码、deploy 目录与入口脚本。"

if [ "$INSTALL_UNITS" = "1" ] && [ -f "$TARGET/deploy/linux/$SERVICE.service" ]; then
  step "安装 systemd 服务单元与请求保护配置"
  install_file "$TARGET/deploy/linux/$SERVICE.service" "/etc/systemd/system/$SERVICE.service"
  mkdir -p "/etc/systemd/system/$SERVICE.service.d"
  if [ -f "$TARGET/deploy/linux/request-protection.conf" ]; then
    install_file "$TARGET/deploy/linux/request-protection.conf" \
                 "/etc/systemd/system/$SERVICE.service.d/90-request-protection.conf"
  fi
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
if curl --noproxy '*' --fail --silent --show-error "http://127.0.0.1:$PORT/health" >/dev/null; then
  echo "本机 /health 正常。"
else
  echo "本机 /health 未通过，请检查日志：journalctl -u $SERVICE -n 60 --no-pager"
fi

echo
echo "完成。部署包仍保留在：$PACKAGE（确认服务正常后可手动删除）"
