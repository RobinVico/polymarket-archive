"""往期仓位监测页 v2 (2026-07-20 用户拍板: 每个仓位卡片默认折叠 — 只显示 标题(去掉尾部那串数字代码)
+ 盈亏%/$; 旁边「详情」按钮点开展开回原样)。

隔离铁律 (CLAUDE.md): **绝不改 dashboard.py**。做法 = import 它的 HISTORY_HTML, 运行时注入一小段
<style> + <script> (在原脚本之后**重定义** renderClosedRowList 为折叠版; 后定义者胜, 列表渲染是
fetch 之后 async 触发, 那时我的版本已生效)。/history 路由由 autobot 覆盖成本页。

**继承不改**: 分析/图表/CSV导出/展开后的 sell-card 全部原样走 dashboard 的现成 HTML + 只读
/api/history/* 接口。折叠只影响"进行中/已结算"两块的仓位行。以后 dashboard 的 history 若从老项目
同步更新, 本页自动继承 (只有 renderClosedRowList 被我覆盖)。
"""
import logging

log = logging.getLogger("auto_history")

# 注入内容 (放在原 HISTORY_HTML 的 </body> 前)。注意: 会过 render_template_string, 故绝不能含
# Jinja 记号 {{ }} / {% %} / {# #} —— 下面只用单花括号(CSS/JS)和 ${}(无), 安全。
_INJECT = r"""
<style>
/* 折叠版仓位行 (2026-07-20) */
details.hist-pos{border:1px solid var(--bd);border-radius:10px;background:var(--sf0);margin-bottom:8px;overflow:hidden;transition:border-color .15s}
details.hist-pos:hover{border-color:rgba(0,200,255,0.35)}
details.hist-pos>summary{list-style:none;cursor:pointer;user-select:none;display:flex;align-items:center;gap:14px;padding:13px 16px}
details.hist-pos>summary::-webkit-details-marker{display:none}
details.hist-pos[open]>summary{border-bottom:1px solid var(--bd)}
.hp-name{flex:1;font-weight:600;font-size:13.5px;color:var(--tx);white-space:normal;line-height:1.35;word-break:break-word}
.hp-pnl{font-family:'JetBrains Mono';font-weight:700;font-size:15px;white-space:nowrap}
.hp-btn{font-size:11px;font-weight:600;color:#00c8ff;border:1px solid rgba(0,200,255,0.4);border-radius:7px;padding:5px 12px;white-space:nowrap}
.hp-btn::before{content:'详情 ▸'}
details.hist-pos[open] .hp-btn::before{content:'收起 ▾'}
.hist-pos-body{padding:8px 14px 14px}
.hist-pos-body .lr{padding:0}
.hist-pos-body .lt{display:none}
</style>
<script>
/* 去掉标题尾部那串数字代码 (如 slug 结尾的 -20260622191708361); 只削≥6位的纯数字尾巴,
   不动 "2400 measles" / "2026" 之类有意义的短数字。破折号转空格便于阅读。 */
function acStripCode(t){
  var s=String(t==null?'':t);
  s=s.replace(/[-_ ]?[0-9]{6,}$/,'');
  s=s.replace(/-/g,' ').trim();
  return s||'—';
}
/* 覆盖: 每个仓位默认折叠 (标题去码 + 汇总盈亏 + 详情按钮); 展开 = 原来的 sell-card 明细, 一模一样 */
renderClosedRowList = function(rows, mode){
  return rows.map(function(r){
    var cards = r.sells.map(function(s){return renderSellCard(s, mode);}).join('');
    var tp=0, tc=0, hasP=false;
    r.sells.forEach(function(s){ if(s.pnl!=null){tp+=s.pnl; hasP=true;} if(s.cost!=null){tc+=s.cost;} });
    var roi=(tc>0)?(tp/tc*100):null;
    var pc=!hasP?'#888':(tp>0.01?'#00a884':(tp<-0.01?'#b00000':'#888'));
    var pStr=!hasP?'—':((tp>=0?'+$':'-$')+Math.abs(tp).toFixed(2));
    var rStr=(roi==null)?'':(' ('+(roi>=0?'+':'')+roi.toFixed(1)+'%)');
    var curStr=(r.cur_price!=null)?('现价 $'+r.cur_price.toFixed(3)+' · '):'';
    var body='<div class="lr"><div class="lt">'+(r.latest_sell_date||'')+'</div><div class="ldd">'
      +'<div class="ev-title">'+(r.title||'—')+' <span style="color:var(--tx3);font-weight:400;margin-left:6px">'
      +curStr+'卖了 '+r.sell_count+' 次</span></div>'
      +'<div class="sell-cards-wrap">'+cards+'</div></div></div>';
    return '<details class="hist-pos"><summary class="hist-pos-sum">'
      +'<span class="hp-name">'+acStripCode(r.title)+'</span>'
      +'<span class="hp-pnl" style="color:'+pc+'">'+pStr+rStr+'</span>'
      +'<span class="hp-btn"></span>'
      +'</summary><div class="hist-pos-body">'+body+'</div></details>';
  }).join('');
};
</script>
"""


def register_routes(app):
    """返回覆盖用的 view 函数; autobot 用它替换 dashboard 的 /history。"""
    from flask import render_template_string
    from modules.dashboard import HISTORY_HTML
    from modules.version import VERSION

    _html = HISTORY_HTML.replace("</body>", _INJECT + "</body>", 1)
    if _INJECT not in _html:
        log.warning("auto_history: 没找到 </body> 注入点, 折叠版可能未生效 (页面照常出, 只是不折叠)")

    def history_v2():
        from modules.db import init_db
        init_db()
        return render_template_string(_html, ver=VERSION)

    return history_v2
