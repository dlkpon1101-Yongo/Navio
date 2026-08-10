#!/bin/bash
# Navio 一键部署脚本 — 从仓库根目录执行
# 用法: ./deploy.sh [命令]

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
Navio 一键部署脚本

用法: ./deploy.sh [命令]

命令:
    up         构建镜像并启动所有服务（首次部署）
    down       停止并移除所有服务（保留数据卷）
    restart    重启所有服务
    rebuild    强制重新构建镜像并重建容器
    status     查看服务状态
    logs       查看日志（可选指定服务名: redis/chromadb/prometheus/navio/frontend）
    health     执行健康检查
    clean      停止并删除所有服务与数据卷（数据不可恢复！）
    help       显示此帮助

示例:
    ./deploy.sh up
    ./deploy.sh logs navio
    ./deploy.sh rebuild

EOF
}

ensure_env() {
    if [ ! -f .env ]; then
        warn "未找到 .env，将使用默认配置。"
        warn "请复制 .env.template 为 .env 并填写 ANTHROPIC_API_KEY 后再启动。"
    fi
}

cmd_up() {
    ensure_env
    info "构建并启动所有服务..."
    docker compose up -d --build
    info "✓ 服务已启动"
    info "  前端控制台: http://localhost:5174"
    info "  API 文档:    http://localhost:8000/docs"
    info "  监控面板:    http://localhost:9090"
}

cmd_down() {
    docker compose down
    info "✓ 服务已停止（数据卷已保留）"
}

cmd_restart() {
    docker compose restart
    info "✓ 服务已重启"
}

cmd_rebuild() {
    ensure_env
    docker compose up -d --build --force-recreate
    info "✓ 镜像已重新构建并启动"
}

cmd_status() {
    docker compose ps
}

cmd_logs() {
    local service="${2:-}"
    if [ -n "$service" ]; then
        docker compose logs -f "$service"
    else
        docker compose logs -f
    fi
}

cmd_health() {
    echo "检查后端健康状态..."
    if curl -sf http://localhost:8000/health > /dev/null; then
        info "✓ 后端健康"
    else
        error "✗ 后端不健康（请确认已执行 ./deploy.sh up）"
        exit 1
    fi
    echo "检查前端..."
    if curl -sf http://localhost:5174 > /dev/null; then
        info "✓ 前端健康"
    else
        error "✗ 前端不可访问"
        exit 1
    fi
}

cmd_clean() {
    echo -n "确认删除所有容器和数据卷？此操作不可恢复 (y/N): "
    read -r -n 1 reply
    echo
    case "$reply" in
        y|Y)
            docker compose down -v
            info "✓ 已清理所有服务与数据"
            ;;
        *)
            info "已取消"
            ;;
    esac
}

case "${1:-help}" in
    up)       cmd_up ;;
    down)     cmd_down ;;
    restart)  cmd_restart ;;
    rebuild)  cmd_rebuild ;;
    status)   cmd_status ;;
    logs)     cmd_logs "$@" ;;
    health)   cmd_health ;;
    clean)    cmd_clean ;;
    help|-h|--help) show_help ;;
    *)
        error "未知命令: $1"
        show_help
        exit 1
        ;;
esac
