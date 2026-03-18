# 排行榜 UI v2 样式优化说明

## 改动原则
**只改 CSS，不动任何 HTML 结构和 JS 数据输出**

## 具体改动

### 1. 颜色与对比度微调
- 背景色更深一点（#111118 vs #12121a）
- 边框更细腻（0.05 vs 0.06 透明度）
- 文字对比度略微降低（更柔和）

### 2. 间距优化（8px 基准）
- 容器内边距：24px → 使用 CSS 变量
- 头部下边距：32px → 使用 CSS 变量
- 卡片间距：8px → 10px
- 列表行内边距：14px 18px → 16px 20px

### 3. 字体大小微调
- 页面标题：28px → 32px
- 日期文字：13px → 14px
- 门店名：14px → 15px
- 门店副标题：11px → 12px
- 指标数值：15px → 16px
- 颁奖台订单数：40px → 42px（第一名 48px → 50px）

### 4. 圆角统一
- 小圆角：8px → 10px
- 中圆角：12px → 14px
- 大圆角：16px → 18px
- 超大圆角：24px → 22px

### 5. 按钮优化
- 内边距：8px 14px → 9px 16px
- 日期按钮：8px 16px → 9px 18px
- 箭头按钮：36px → 38px
- hover 增加轻微上移效果

### 6. 排名圆圈
- 尺寸：48px → 44px（更紧凑）
- 字号统一为 13px

### 7. 颁奖台卡片
- 内边距：24px 20px → 28px 20px
- 卡片间距：16px → 14px

## 视觉效果
- 整体更紧凑、更统一
- 层级更分明（标题更大、间距更规律）
- 交互反馈更明显（hover 有上移）
- 移动端友好（响应式未动）

## 回退方式
如果不满意，直接用原版文件：
```bash
scp ~/clawd/projects/store-ranking/server-ui-v2/index-original.html tencent-nofx:/home/ubuntu/nofx-Metroll/dist/ranking/index.html
```
