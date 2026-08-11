"""Kaggriculture tournament agent.

The policy combines a replay-derived opening with an observation-only task
scheduler.  It is deliberately self-contained because Kaggle executes this
file as the submission artifact.
"""

from __future__ import annotations

import base64
import json
import zlib


CROPS = {
    "WHEAT": {"seed": 10, "first": 2, "max_day": 4, "max_yield": 6, "ongoing": False, "last_plant": 24},
    "CARROT": {"seed": 20, "first": 2, "max_day": 3, "max_yield": 4, "ongoing": False, "last_plant": 25},
    "TOMATO": {"seed": 50, "first": 8, "max_day": 8, "max_yield": 4, "ongoing": True, "last_plant": 17},
    "STRAWBERRY": {"seed": 100, "first": 10, "max_day": 10, "max_yield": 4, "ongoing": True, "last_plant": 14},
    "MELON": {"seed": 80, "first": 10, "max_day": 12, "max_yield": 6, "ongoing": False, "last_plant": 16},
}

ANIMALS = {
    "COW": {"cost": 400, "product": "MILK"},
    "SHEEP": {"cost": 500, "product": "WOOL"},
}

SELLABLE = ("MILK", "WOOL", "MELON", "STRAWBERRY", "CARROT", "TOMATO", "EGG")
MAX_ORDERS = 10

# The opening deliberately mixes quick wheat cash-flow with a smaller melon
# position.  A previous melon-heavy opening could sit at zero cash for twelve
# days and lose all livestock after a one-dollar within-turn price move.
# Sites are ordered by expansion phase: four initial, five in NE, five in SW.
ANIMAL_SITES = (
    (4, 2), (4, 3), (3, 4), (4, 4),
    (6, 2), (5, 3), (7, 3), (5, 4), (7, 4),
    (3, 5), (4, 5), (3, 6), (4, 6), (4, 7),
)

DEFAULT_STRATEGY = {
    "hands": 13,
    "cows": 8,
    "sheep": 6,
    "strawberries": 34,
    "strawberry_last_plant": 18,
    # None sells fertilizer; 1.0/1.5 require that multiple of its sale value.
    "fertilizer_roi": 1.5,
    "opening_wheat": 10,
    "opening_melons": 9,
    "opening_carrots": 2,
    "opening_animals": 2,
    "opening_cows": None,
    "opening_sheep": None,
    "crop_transition_day": 5,
    "strawberry_activation_day": 4,
    "strawberry_staging": False,
    "opening_melon_day0_cap": None,
    "opening_melon_early_cap": None,
    "top_hire_ramp": False,
    "land_ne_day": 5,
    "land_sw_day": 10,
    "animal_nw_day": 4,
    "animal_ne_day": 8,
    "animal_sw_day": 12,
    "feed_days_buffer": 1,
    "ongoing_harvest_threshold": 3,
    "drop_load_threshold": 30,
    "price_adaptive_animals": False,
    "animal_price_sensitivity": 2.0,
    "zoned_workers": False,
    "use_fixed_schedule": True,
    "fixed_schedule_version": "v14",
    "v11_radiant_player": 0,
    "v11_radiant_variant": "adaptive",
    "v11_route_step": 109,
    "v11_alpha_milk_price": 193,
    "v11_radiant_market_interference": False,
    "v12_late_market_mode": "price",
    "v12_market_interference": False,
    # v13 keeps one coherent production route and gates only a compatible
    # market-order expert.  The gate is evaluated daily and held for at least
    # one day so borderline public portfolios cannot cause turn-level churn.
    "v13_market_adaptation": True,
    "v13_gate_confidence": 0.70,
    "v13_gate_exposure_scale": 6.0,
    "v13_gate_concentration": 0.50,
    "v13_gate_lock_steps": 24,
    "v13_interference_min_exposure": 2.0,
    # v14 keeps the same validated route and daily hysteresis, but makes the
    # gate concentration price-aware.  A product at the $1 floor is weak
    # collision evidence; a high-value visible pipeline deserves more weight.
    "v14_market_adaptation": True,
    "v14_gate_confidence": 0.70,
    "v14_gate_exposure_scale": 6.0,
    "v14_gate_concentration": 0.50,
    "v14_gate_lock_steps": 24,
    "v14_interference_min_exposure": 2.0,
    # Observation-gated overlays keep the validated movement executor intact
    # while adapting purchases to the opponent's public farm.  They are kept
    # independently switchable so every source of alpha can be ablated.
    "fixed_board_adaptation": False,
    "adaptive_animal_mode": "mirror",
    "adaptive_animal_min_day": 2,
    "adaptive_animal_max_day": 14,
    "adaptive_animal_min_herd": 4,
    "adaptive_animal_lead": 2,
    "adaptive_animal_target_share": 0.72,
    "adaptive_tempo_cow": False,
    "adaptive_tempo_animal_lead": 1,
    "adaptive_tempo_land_lead": 1,
    "adaptive_capital_priority": False,
    "adaptive_capital_max_day": 12,
    "adaptive_capital_animal_lead": 2,
    "adaptive_capital_land_lead": 1,
    # v10 uses the validated venks balanced executor and changes only the
    # order of non-wheat sales. Wheat buy/sell order is part of the executor's
    # cash-flow cycle and must remain untouched.
    # Earlier sales move the shared price before a later opponent sale, so the
    # overlay prioritizes products visible in the opponent's farm pipeline.
    "market_interference": True,
    "interference_sell_first": True,
    "interference_targeted_sort": False,
    "interference_preserve_wheat_order": True,
    "interference_collision_only": False,
    "interference_min_exposure": 0.5,
    # Extra wheat purchases are intentionally disabled by default.  They are
    # exposed for ablation, but only a very constrained one-unit action can
    # pass the safety gate because feed-price attacks can damage our own v8
    # cash-flow more than the opponent's.
    "interference_wheat_squeeze": False,
    "interference_wheat_units": 1,
    "interference_wheat_price_cap": 30,
    "interference_wheat_min_opponent_animals": 10,
    "interference_wheat_min_cash": 10000,
    "cash_reserve": 150,
    "price_buffer_pct": 5,
    "animal_daily_cap": 3,
    "wheat_rush_animal_cap": 1,
    # Adaptive profiles are deliberately expressed as ordinary scalar
    # settings so local searches can tune them without changing submission
    # code.  The opening remains common; public farm state changes the
    # expansion portfolio only after enough evidence has accumulated.
    "wheat_rush_cash_reserve": 150,
    "livestock_cows": 12,
    "livestock_sheep": 2,
    "livestock_strawberries": 34,
    "livestock_tomatoes": 0,
    "livestock_cash_reserve": 150,
    "livestock_animal_cap": 3,
    "premium_cows": 8,
    "premium_sheep": 6,
    "premium_strawberries": 34,
    "premium_tomatoes": 0,
    "premium_cash_reserve": 250,
    "premium_animal_cap": 3,
    "early_liquidity_floor": 0,
    # Soft-gated experts.  Strong public evidence reaches the proven v5
    # counter target; ambiguous evidence interpolates with the v3-like base.
    "cow_expert_cows": 12,
    "cow_expert_sheep": 2,
    "sheep_expert_cows": 2,
    "sheep_expert_sheep": 12,
    "rotation_evidence_threshold": 0.9,
    "force_expert": None,
}
STRATEGY = dict(DEFAULT_STRATEGY)
OPENING_CROP_PLAN = {}
_OPPONENT_STYLE = None
_EXPERT_EVIDENCE = {}
_MARKET_ANIMAL_SHARE = None
_V11_SELECTED_RADIANT_VARIANT = None
_V13_MARKET_MODE = "BASE"
_V13_MARKET_CONFIDENCE = 0.0
_V13_MARKET_LOCK_UNTIL = -1
_V14_MARKET_MODE = "BASE"
_V14_MARKET_CONFIDENCE = 0.0
_V14_MARKET_LOCK_UNTIL = -1

# Exact public action sequence from venks episode 89418172. The schedule is
# observation-independent: it uses only the current step and therefore does
# not identify or special-case an opponent. The adaptive engine below remains
# available as a fallback and as the experimentation surface.
_FIXED_SCHEDULE_B85 = (
    "c-rk<%Whm*a{L#rxlmP+dU(f{YDU7aTY?@Y#)8mjV8$?Dj2CV14F9_|&El=9n~{-`dGZ#?Zmv`y#k%KxGvh==e*NFGfB)szfBgN|"
    "vw!(|_TlQ&r?YS8XaDibfBo&hzyIL-$AA3t>wo_Jf4+bIdiM6+$L;su9(?%W%U^%K`sv+|SJ!9fXRqJioSkp(e*9^>ee?Z?KW?wz"
    "|8#c#{M)zxJ3oBV4`1G0zxnz5^FDw1?YpK&em%R{e){~|xBvA1<L9?$-;Nvc&+q>5@%@`GuRnkP`kS}gtMC7=p83uC^me=b@cqBc"
    "TkzrC>%V;YaM$kDQ4^-$O@F*^&iP#nkK6TWdwsoc(E6?!rm5?FOXm%`zIwggwFeK#e9-#Z<c-b#PY>F|n(^uVm))oN_%=1|Pybw3"
    "N6pzk+&0Wi^4GK1SHF#Yyr}G`%y!4&qtU0^|6l9(Dt`F(>Uf`=&zF$Wf|Wk<caJ&TC%fm}Zj)ULe)>G^`~7%(+qpa*b{$L)y1Dwi"
    "{fO6P(@@;4@`I=E7yh(e!Cu&ZVbew>OVUn-S)|>&0FAsf?cp<~K?S3GyA*o*Vh4>4qp+%mw)lQLmtWKN>2yhtyl+-x%lKel9iDeh"
    "<FM;%u)g`~D-Xo(3{xlJ_7za;_-6j>-TMSS8*Gc)DO27tn~{ZZ(En-h6VFccpFR6vBu>=t>Fr*6bf()R)~ojJ+$0O(+q)3;Z{p|h"
    "Kz524UcbM--oF0)^PjdKKfk+v_iuNHE^U*($!o2f$M#N?i4Nk9D1SdV!6>n&6g%uZX}=YwHrW#}*Gc@KY4g4L`2GXjg>Wexd<)4p"
    "_saqvHPa)f?Vf(N61uy`N_5cJ<bIXO(Na%~yHWh&dX~}C6OcfJuh^a*fhW5!)>M~R+%)pN;8oGmUK{RA$Lt~l&!YR0evn+L`D>q="
    "`|z7v4CXF=d(WV^*l9w!i$6*zM}xZMLpeM+bBGQP({PWYrvp5rBbeJa03oK?9kq&L^eKLmfM6Ojf_MiZLeudu|4~EW2H=PN<Borl"
    "3*01ZA?{Emgrksx-YF1CxpU9I*gty9F`YYv!Kj8ootu@U#?DR({a(GnHmYM^%rmQMTvvUf{>9Tl_DH_h=CrdX<x^VnH2Z-*?ciMe"
    "^!ek}%@5m;AOE`G6HoNDBaz@!#P<Z=b%S>Y|KUX7opvW*jQ6G^4a{#NOvfUWY`C{hY-I4Xk!TMj&AX`Y;K*Gr;sf2<$I&AJpZ#J#"
    "xNJh}oPjd~3-3$w@g9vI6W`3ja4>j@9ScG}KcncK9tp;o&ZCi-01Vdjb&2pe_r*iOpN%CuFH?la^~A8`dq?JzeC>j0pUE$uVm~eR"
    "J3$aQ$jVwK9Bf4bvw`7qkf0DEE)pvyA9s?daWE^E-s@fv*%nP!dRGY~o!|>G#0p)dce9*ey3EBe3!9aJ4x`IA@BXYtfJIm_h?d7X"
    "1n!VY{MR~N%EjcqF<!VadPSLJ=N0;p<lv2UqURBrkh=c~EmLj3Bn()Wic{AQD^5LkUyZA$81@ev!%j~+eF*E~kBdaGVE}Zha5nee"
    ");H}4CRz<=K@T)^^!{Md;c#~P8WcO<LpYo7o`#jC5|dNUkQBeB6&T}EkKbu%*7F1sn=Sr;g@ViJ^`d<L0tj)XTfZZw<sUbu73i3!"
    "iD|RM%+pdd-(G$ESB0+H+Ibe?rXTI8ZP0~&QpB95aQe|Bde!be)xre+I@i;qTsOeYWWviMf9wU9j9>)!ht2!<*T9}czjr5cfH_Vp"
    "bsoB^tTRV64ZG3eM*9m5ne#r$=%>w^k(A{LMbQ3}H3P9fnKdI7DI?F5>HEMA$SeYCRkMyS2rTYv0_iGS+n&mPu%1eu{HEe(#N;v8"
    "PY0})Fy<{%TS(-rKY+OcfJZ4$7)YbTWZ-nz@Wx`p&rcLbKOYT3U2CFboP4odoE!qI>}1cRBvmlBMb~7#6Z(>g0_!&YQW(oD02KoL"
    "Njb_#p*9V=iLp#dU!Q4)AApxr3=o1-@Utlf7jla1{rQoj7>XZlz+38!J^d8izbB)xQH^ijwMvGo>=g>oThM}m<OxtN3~_zmh~2>O"
    "+beB55``D&v@1O7B26a%<*~Iz6m!Czl@vQm;<;q^Dl$6uh=J)N&yEQ#QevPe_7-}85<CydVpwGJ+`*nVk1l3DGE+SOCm%}SeD^Aw"
    "4%;EF!qoB~-(CM@H;lcJG=PBgVMTVkNg#ZB@f<#NZVV7b{JGnY1Z)Lj<Y;0EvLw%@@J^k^ZQq_NjBVLp(KZR;ns&tl8$kb7x@Osp"
    "+4a>=Z_d6|@R<FpB$4GNmcI|!UY0Nx&;^)z%8|=uyaN;n)wYz_!E!&rg!k6;Fk<<9I291~mWN8P%48<g2bogfE3PELd2>nDT9)q|"
    "HWEZ$5|lFFz8O)s!D{f6?!|mMX;N?fu@PL~JCJs^r{MuFRJsxbgW=7{+e@EeHjv7zHb0CSPmc|4aP^~(<2r#}P#FceDXQ@>HVtZJ"
    ">*c(kV*iq(Hj<lfW9k5lnMyE8N4wYzqZK#DRVys}&GH_?FUTVxO-am6tH8h4niq-Il&(}@VoM44LVsQ;MM&DHRIm#$mH@NU5reZ?"
    "t7Y%7OX7uzIDZRYN%0=oTv69nR3>EAIS(Kt*rsPj=esprfWeCdAZsaX5B?vjTo2)T*Lf46zbxE7Nq%~)m0+`$_%G8_C%}a<{B>qy"
    "2S1J&8B;GkdOW!oVof?~`o5#u5U3Z4<TCL_V0sZS>Ezyyioxql90LA<X@-qpyr-7)oDHH4VbKu+R$w@}`pR4<2GzEgO*$Ie1XqnD"
    "?aa>xJ&S)Dpt37@C-sPeH-~s~Go%G_<I2X4Qs{i!g=ULTZFX5big}y6tR^*zA^4pjcr968lB?5)(F$t;O<{rGnCBPnm26XrJu8h_"
    "SN_zqY^7wU+^)^T&9`5sE|izew-0}4aVxCnsZ8U`MRIK2DXMHru-Gap&{OerbS9y}vYCROV!jOeJfc%ujb1dfyJvBJI^Yb?O<@}D"
    "Xx!<z#-USQ)FR4*Vt@sF55G7ZjzOof1Ti@W;P!8F_*MwRDqI+s&kenIqlub5#Crx3WjBPV=@5ln<xy_@?5qY*fF~n6w`p=SV_4$y"
    "Qn6S8Vp-R(-e3?wQ6bRenP8t#iGnhb3YA#%5mCU$b6(KowpX|_P91w%xmLT4J)8$i&Q^>NrpBFngMTb1-OS?a-QQn+tAWGl;5zIS"
    ";t3mv=CDKqW|K<XLsr=q5Ug<9(Z&@?F+LShsL3<u6H#o9iYVF9<Fb~jcL#KYX`AfY;0L5~gpffbs$hV&fNp^=u%{_&`Qi2z76dIm"
    "zu#d;^1_YNcJLOn2ah4th2#Hn7`?db{7cJASY6_CZgI8%ev4f`N^Zbv^FYB0ux@?+<htQby03~f2VXo8AbrtJXP*lmI%ki!P$v?A"
    "-6vm?U3AVANHr?<;hIBa8OdR}g*%if0m|aA$U3-XwO4SA2#P{#arKQ)0t$ldJ9Up%+JG@yF7jSTDsF)2({eGb>K8}Ji2J`)-7VBp"
    "h{H6L+f2n1EhG$eu$f$fMe!8$m_^LvnsvJsX}M0q+@<5KlT#Dcn_xWAFj|S8!i<sP_jqf9_A5hA6=^g-Et!bfMGO3mw#u4~pr`@h"
    "izcC#xMNN>KkHOn*}9d^R9r0?BoJgJ5O#1wGI&MIRCug&ghdyZFAHFCkEQ`Sa3Q4DcNHqgb-(6`;o`&{vruzHb+)CQ9b~FU%0cHZ"
    "rW$%Tw^Ir{(uiH3T4B#6q|N9$!xOB_L%@NTw-omoY}r~tc<!FJaa%5GAjUniUM`-{qD9am%p*?X7FD=t3EYU;!yTC<RPZDJ7W~8%"
    "8L%*I)~tC_j6*9bNhV@#ARvjbPbd_Sw9t~NG7$p||32v|SCQ6B_OTWril#y&h0uPbvM2jW_Ju%ePkX`Js_BF(NfjIh7*GM&C6z4#"
    ";zoWEtuwCM8sK)mkNj=gMO*KjgCP3KF|!D_Z6EdF7%wDg!A}WSXeE-$b*WDG@kC(VQ8;nLI+U&)p$+yp;@Cp0aAG-2k@?32?;7xp"
    "@CllIWGsJbMM)!0$HB{ew?~vM!YFfYOj-1Br}aO<D}y1;q5g)cHU}tagze#`rJTc+I>NdRF0gD+<BpdSb8<>3qlUUd!W2RJiI*1y"
    "SHek67;GlaWa28XAEm04PLkm*1nzATKCg_Rs`ikg`vq=O3F6!Jh#P|n-qH$08L3Y-lcWQ760qi2hB&o16?BDWp<d}l4Lw^g<;-&F"
    "w)Ewr#MAtdfBx{`v^o!{W-ImbL<rl7nOO^RIf5Bt;*C9)W#K5sCK^N9L?TuMwCUWks)0(~u3?d?${k%|aB25)B&-I4<uRFO6)a7Y"
    "p`6k4qI)(|h`=%5TotI4_la5)ZUxPf4kqg?yKXvF)JA?D9#0`JYoqyg7M-Dpagip=6Xv*DlRDZFl;I^3*v1NnaK@iKaj@`Bv%MOq"
    "3_(0zxD!r<UFm2J_t7kuW2D|U;Qm7t0^xq=K<IOgP)Oz`;Z;NPWt5IeRzV$-UWk|x7}3&4SP9ssSy50>Zac^9aWsb;KF3Y=Y&v2F"
    "+B)@7>yXB_m0+5L%|5Le&q!FHBzFmb835YBHHKf|R_Q?qJ$7M*i38#8ax+?Y)Bh9tDKEP0x$vw@PIw559TP#%m*JLq8cu#eb<fN)"
    "9zADklHUuLEMbn6fc*lakfG_@EZcYP0i_jY$<xZpsZr#tq;fdySq{7Hr+&RXuvmx1-@uh3ZhSz&Y9qsi!>%g9SYDMt`1+v|i$zfc"
    "0L&0h)>_Q4oI+XFE*dnRLK-1w$+9h%#0qm5FO_tO<?e-?a<qHoAVR^iF4FaI$b|cs*mAq#sQQK`w;HFclADKR*cf9GTyS`!nhe#I"
    "EZ6prLE;Gf)3*pPRG(FjBbUmr%%$>WCMN`3T*BqnIO22+nn5}dKBq?I0k+i%{*d9OV=EYx0g_<elE*Su0LB4B3o2Af)b*?E>Wq|E"
    "DqBm(mXfS04#%uKxHi7bF(`p<)C7wb`=ZU4Ifmd^<e&|4be>~qBc|Zi_nQ`zMoL*R*uf=9kGtUM`7SG6OTw5`1bjC`x9yD9oFY-Y"
    "9G58W7Xz`cGHrP>vHIQ05;=N=qR|H^ON@{rsL&&Q(|dkDtI$SKl;FX9AUjtbOZr2#Pc(;p<+jVLC?+@&Z_Saj)xGglEdL3BNGkH@"
    "j!DC6Q*lz}MG{Eh_HXF|3F_k8s8JWI-4kvd68*{y!deG_&$&><Das}?I81u2bBAE6X97p-i5Z&Wk-{`@6$;4!zbNbNh0U7L+Mq~T"
    "Q@txTqEsvy3W$RmNp)oCaM<KgJpeg&SL@-M+f((<_DIg$OEb9Mx+~b^T6j(H5Tn3&7@QuLzsqhBB;(}P>H-vRK}y{a0`?`j`<W~`"
    "QziTxEUuk20%zV^9TUNP1r^V1uyz<y)iK_z071cS6us;~fwSGwb>m+TCQ7XX+?TypOSNG0XxD;lq+4w0wgMV>!i576xnAf`pwUAE"
    "jW~s>O?&5G-#h@y(e%S(;j(LFmFFPw7`;Cy)=R&OH*CJG&p1H@sOSPiEfxZm)Mlxot<=~^FF+@bcWez2lZy6(2MIcXBNgzlvcqnx"
    "y&a$@d3|5SYYRyaO@hVCO@r93i`Zq~X>=V41Ue00aRX2?+`6llCU?{w8YuIwtO6xTJR3w&8pM}W^0*;QWhlO?ZDVK70JnfiM`Q{t"
    "(a@q{cZ~nS?K)TY>l46A_R&J?TiujuK|PgXMaI&Z<PCjjpHOrehZhXF;a829X7RY&lZ`@hf+B3d><Eq+iP0r8Cyx8K(PxU;79tZH"
    "U{EjZaV}l2P1ePz9Ff}XGZc(Qv%DVC$jltVT9_-!<_D<6w($$RHZ_LKa`(NmhL_GwmcS#-%%wgv)MXA8kGX4PIBOaWjxmjdnK_*e"
    "l*z&Y!t}gP2lto+Z-d3?9~=B68#+B~qLPlH9WFHimGb|K;^Y!KJ_V6-Mcg-RV3lOz6CbD^-3%wtfg7dZF4jU95!~2@9*&z>MXA47"
    "-F|tyC(%JiGP23fPY>^d;B$c30uYQaMGq%@aOshYN>=SrLyN)?yMwjGNpkqwUd&(Rs6*EUInF4uP78(JPKMT^SXA_8+G3z73syMA"
    "BTa589g}Wa0hAlsCp_*eK#Pvr%6vkN$Qak!s^DJ&{2irBaGSdDSk4EG1uE)>a+k21r&m_WZgpmWEb(52nL5o?PE@xtes_`f`_cgT"
    "_yl3fLeWj0>Y3>Rk5{gp{Pf^?=O6XN%24s3M@|NL5nbOXSIJ^F33WSL1k9Z+xIROrIXqI@fJppR7su$3Gi2S!BM+n}cF}``ces+Q"
    "t5BZ%PB|^i1HqdSo>6dd$}UqH1!@#>Oqw5v{E9{cZ@vNv^@tWsp+&q~4WA=wh-|X0VHtxEM%DQ_kaZ!I<Cvqu=&oRbIYDp=@h3*A"
    "@x8LT1&tQhx>1e1cpNfJ%<BOGLHGtCS<!Jn3>W*>90l|2Y)R(yq<Y<wD$|57(hxcYPUmT|`;}`<KO)vqKp7G<G#+)MnzD(wnw)Fj"
    "WoPyHzd9q1r41GE>iBWU8jk`IR7Y464KhXvmB6apCPJR63v{&daqQ87qR?AQY*BZZy+_<s$G%<Lr+zuV9$lA62U8@|+@5I+QkDd1"
    "s2y}2Q3nN{?I~vZR_mqFC4ob}%qu4>Y*Gk~BO*e_6dGs5pW?46jW^Xx9<l><WYhhOj^Gn^^vAF>;^5IEu`?2|BONbN&9MjX_Xn5c"
    "4bj9?R#O*tl(sesy<PLL&521RQLZamP|;TggS3`JHVDQC@z(^fgp8;bLTa4**J$ZQzlS%-dYXP3>_((*Y35Hf5$nST6{%2&XapIe"
    "Zlw>%2#htRaZ+@xS6PKCl_ZNQKS{<%$6z3UJVx_=Do0|-6*o7E;2>I#E<$di3@k8x<C(FNsgZi{jDmrWb9mMPXWiNF2z<3#3!DQ7"
    "rlOg9Kun^ngaSeszyp#4H2o!*kko$C?1oS`@KRtku;TWCNd^}~U}QM10SFsfQBOxgQ}Nic1~*`YkZ&CEbH4qZV0E0pmZnjre$&(q"
    "4*lh^`YmM_#58nL-Mg%yEnET5hjEr8RAnupDlhL>b9MQoxvFWdIAP*<Ve<o%cpqSad<%9DQk?t_<&jc%E4amHmkWU*&`FX&zVKKy"
    "$mCYwM{PJ5ryfP_E{9XfN$GKkDg$$zgh^6zqjIm+m^x?yx(EeGn9zz}7DfnQD~T)wC^;vF;sJ4ur2a`^WEVc{k)fDlD$|DLtuns6"
    "G8h|JpjRxQWQh=)3kDm9OVJ|$PDykR$02Ny4~f|Bu@YRK4M(iQAmE2s&1<qjm87kd3N{8P1{F9d*5D^`J%kbX#tkad^ZJd+p&jse"
    "5ut?u1B(?rB^q4`&BJ(2kU%p;H3vPha_j7Vq^=-qSsD;_+%0RsT1lF#v$DmZ<J4;Hx(FwTXaEn{_lr2}=Y)!a#_W86nMUgFS^TWv"
    "h)wrS2p7F*qUEfQ=r_Ci@)kVuO5Gp**QGsv##lTTPb{9L{iRi-pa*UBW1ywB->h^Q&*CM`G(T#(dSOE2vws%xpq61W%4|_fW~T(g"
    "y7dC3=_p`fC@ZO`!ft#sYD<@hS_ak@mACZQRs*jSwaqq>bF4$`L=bIyB_@X+;X0xS<8~0+a)m>oG>ULrc$fV~krdK?nf@izM+vxv"
    "1c^K~y6c<h)fC8v>$F1P72&HG#gb*Q;s~s(n!n{LZ6l(F=gxlSz8z9X-_+A2iGez|!Ob7Bh=wd<0k*IoW)6_xc2RdAu3HN2yj5rH"
    "b;<{q%~8nUqVQIe(f7J&g&VqzQRlAcbdgSsweI<?xy(4qxMU?_AHiXr*$mB4Y~^Enar`$7fZBiG+~5X7N&rr<VxVvmFH(mgB=vfi"
    "0|3%N?`^k6Sj`W7T@w^ivnl3ogqCEYBZ-*-N1z)YNIXT&#=U7)Jl)>8C{#?lYVY=kbya$$z-^ud_ucE5x$6@s#qQNMU`{SNv3i_X"
    "9V<TZxUf2OcqB+-tH*@ZL0!?Q>%-~RKs3m|+2+!?Hu0TOD9$Ml7v<`wEEab|7#f;~xgvk;FApaZ)j}bvB|piPrHAK%RGFd~ExM=`"
    "G;=)_;xJNcuQUnX7RzJvqZ?r(G0BHWplmi9@SR5Mb_=%CwkZ~`=GisPcsht?ys9`^{ThxCGUSqF*H$BbKLPMW#4@4EiV<X*04im9"
    "NmMlU+J^B4!@!zKxN#*1k-*{!6k$1f_%1O~9+%I{NJY6awNk3WRH9`}RI*MrxCwE5fb`7ARiodO!7XWG(I<0}<Z<&6sv~iX7QjWK"
    "qnjBW;o}ejT0>>*Qm_>@FuI$fNchPuk6M8%|N5T0V6jG{H&&@5Lvy0kn+t8|31HeaBPU1SZV8W<-h(fkC%*tt+lHfx_ouMjJSi*}"
    "scNVG@%@^ech|IA+~4Xn1@4&j4Cg0pRjZvsw%E}#CUqNd!dlutU1k^NT|OcBH~_<mXG*b5pFBq#m9An&A`ep&P*Lus)jIJ*pqew-"
    "0Y!GXtUOt?NgM{?ka$<t^?^EHzV<z4YO&qdEFrRjm&lHor9h=Bi9{7~X>LI`DSa0Rp)=)E!}5eaNxWy8ZWNcfgaR*Ei{UL4VtkmR"
    "Rw7So#$KS4J^NVK*hVm-jKy`hj*GV*h%YI+kAa2{d1P$|{HCIzCDvpl)7+RdWeDbsXm#PyL9X~+K#F)7ImaYGzNic~nk68TW^ahl"
    "8j50AEG`g{6G{ghYMn=Tr6a?fS6ol5R0G4(ll(?U((m2~>rnxbUi5lyy`r+o+YR#a$=m!%71_wN+B|xu6-A|&u>I|(S_PF!`i;&9"
    "xK_kTYbjDsINV{)wQbqhEWEa?N+FS7nMp|at-4eUEL=0>eNga_lgr6vSUyF^xlLB>MYu@&D4i?uWRI-^S|!!Uny0dMV^c>ts(WtP"
    "-%|Z4E68N6PF&Ovn3YMD)_h;_C@=Bo6BOEBjC^Gml3uw_OI=9yh^AiIlT9q$$M>*IpctH`b%r9x&<|P#-P<zm9e$IJ4xpdxwn%DP"
    "l=S7;R+}MFAVjMy6)Li@3Jkm?T_DIL(>)~g7KH^B+=en9_K@OH=m(srsV5xS%2@*r_C#d(?ba9;CupAY1oQ^=6Y{oNmjJ?O;5LGC"
    "c%~zObj00u?UHcotM>94SL=Gey~u-#A#eO*8Png*Rl5qJ>k+dqC4>3Oy1-c7>RB&XcS%Lb_Ru{hpQTsA;_%*V;Gdm9ig-%IZ*vN<"
    "=>7Si#lhK&6HI6u1gMwJqkzv)zWt&&_ZsL21a*>Tt=$VvB%l@jof|6%2-S!at3_hE>2#hMV$ox1MJNiIystV}1ahu(LM*7G`3~`$"
    "za{8XP%0Y<V?mlt^K<Sh9l@eK3(T&f5xhtFNqu_|E|~6wc_R_T;#}M{s1L}-)<BKHG{u5_in?S`{G8ypsFhaD1Lh=AB3BOlz9sCy"
    "ZxoIa!vO;RlDMK)x+KZ*NV6A7cs*eR%S;t5Y&awrlRWIU3e1=B#0Th30s-}>=Q6?VOIKdJ(LD4M9l6w}1u(P#PQZD5!T*!CQ`5YF"
    "Rpv_7gylw8sE@ui%?;~}N3=qo0Y?UJyEA~Byh`YpkNc4MO2R&wAvsW(S{FNZw?HEd4J_-}cL28rYd3jGl4j1e&tWgkZq0GJrHc>@"
    "OENE>B$@Xr$$Zeo2Nuy}>TWQPNtUVm>yOyt--9ZXy0zDweX7MF@yH6CFOdKPLyr!(v~=+c@QNf;1Gm=wREuN)RuxkOfrUEH{k2L7"
    "txr>J2a!-o>X=+`OrwU^k}mrVQsY7qNju_GIGt!$kSJ2Q6}gXo*}{us)^I6gRHM9vQ6(cq(aN;kbWqfx_V6i@vf3e25@0|#kO-?S"
    "43~b3B!M@INj$$O=%f#`wR|HP+tRB`0~|EBS|QfP{`P?4q}C*zoioa<5(7^B8Z(g61m0Z7R%T3f0ZLCOptc3^NxLLPv0g+93jZlO"
    "I@&gkk45fr?Q>&K1<S%}X*48X`RTcWtTF2_=q5)O)btmYedfZ;YGKm*;ETOfidZ~JIUgplv_Cn<h+P2$B^GL29%O>h(GfV97l~0W"
    "_#!$@3UB6XdxbHkz~E{CRX9Y1%G=3WHL3)w+g6Lylz<jfn$SQs%t@3Tpq}iL#(+M8H^4w_AxMwmMm*!B7VgfB)agRvnj`E>>I)*)"
    ">sqS)0@M>8;Zbf)M3^_*C0zW_F%;RBu~a(TcI>W`^nyBf30kI%T{BUq6h*eA7_CajV8!4HZ37J<5-Y+*q6D%b)Io7Li|POp0Hsn2"
    "G?l9f=-ZT3MYT-1uTrx9q$nJUa#VpW3b+v(vOz7;2Cs!PvRLL^MXNP|KXkFh5)YpcQCyR$#M?_P^<gG2X9&m(A8rLB0+C`9VP567"
    "Y35wuK5VuyQh3~~cA{z<Mzp0lSc|I+PlWEQpGlmeL3F3_3ia|toSR31?hJxD@Q2uE(~AMB=+1aIqaZnvbL;Nr%u{K+OE#Xg*XL?v"
    "rhABryQJuMq$JR=PkpXd>*BdU!(7V{!2My|AL@Fsj5<=S#!j&jn32@RIGSZ4%HodjB-B3z+l3;=%yh&1kV;SqFGj7<nA!iGHp}w*"
    "tsM9Pb^%g~43YvcM^!swbDz<n9;C0>24yUmD(XF9ZO}SRl9GjDpEcB?RJ#cgwT@XIK32_m0#oL^b>31<SQ4%HWtbHrvY3~oD_R+@"
    "FjLEcx!RcSp^ZdN8gL7K$D6AxT4oA*0LDf95WSwlT;>!>vZ^i&mhM7brdXjo%h-wIaBBkvY_EJmrn6$es*uLBR*TN`fx4`*GJEKV"
    "wv-~ZB<DDZW`0!1#F^&?TJb9D0b{WZRZDq!G^FbB02xIR*~fx#NO`D;Ow+b013>7^0jrDB>q{4IUeJU?Qpu<<(;^oAsTG?kRZ&k@"
    ";8exYWl)?syz0y0*LykbRx?Jhx6t<NriO|;R5)&$aslBxdD?d!fa+s+PQj>>-Cu=uds*ug7{a<rg66pHfLM_15|_z@f|tQ2etFs_"
    "fngYK>PR!}PaZ}q>`$f-TxC}?uC!F&V%ySYF~`o7dPB+NC=H$cpVl!X1ZwgV@2|q9y&Bq?y&q~D;;9W!Z8%jMzWqPXT4Uz"
)
_FIXED_SCHEDULE = json.loads(
    zlib.decompress(base64.b85decode(_FIXED_SCHEDULE_B85)).decode()
)

# v10 balanced executor from venks episode 89448781.  Unlike the rejected
# cow-heavy branch, this schedule improved both current-top train reward and
# temporal holdout robustness.  The v8 schedule remains embedded above for
# rollback and paired ablations.
_V10_SCHEDULE_B85 = (
    "c-rk<O>bM-a{Mn^YhjX-KeE%<e6jH~W5XX2UJPR}Kwc0acv(!c3-aIN8Bv$y?dt04K7A=^Mk^DN#e2SQcb%&0um5}Y@4x)|kH7zV_D^5WK3skJ"
    "boTB1>_2|_uYddR??3qd@gKkZ`k#OQpYNZ)p1pndar^zZ2Ooa;^0%L_etP%g)%Dr=+3WW=XXl%{AAj0z-+ce!kK60_Kb@UF|Mu<w&JUmT!<Tp0"
    "Z+`y%yw6{L|E}qgU(ar~pFaQo?LWQ$`1$SGx8p|q_T3*ozJK%O_2=(jfAe;G_5I(~Grw7%-fp)azW<kb3qHJi{nsxa?%KUNYQprp>5uo#IlpV6"
    "(5~M{<J0!~diJB+md+b=ef4^~YY!ff`JnZ+$s3#9e^?*2hc)BV`!Bms^YLwJ+FyQKS4Yj+KioFVO!C*W*H^!fecYP08I{@YID9nvbo>9MCkazx"
    "9=^Rg-Y4htC6s6Z7<tqEyT=^vlil-fx5=&rKYgC|{eHYt+j(7D2h)RYu0C%+;&s_H6nCrq;OYB?KW$gA7xrJ+v{A{Dv{PXgY4<KbBM%=HjIVvh"
    "G^k*7Z<j((U+kc<VT7w{-nVn_r6u%w8qej|w0$~V(&&BD*mJgw5BAmJdB@taa@%6YVb|ASee=~<9*Er;rcT1`E1=eKbC&GhC-B)|Tii|=e#d~2"
    "r@9ah`acbR;@OG*vu7WS#EJSnz1>TX&UBl^dez>Yn`9w;dl#bqP5c}l$W9T%>-X2!+t;6e{>%2`=Xcld{`KzArEStTd98Kx*xrdU<-mVk9h_j4"
    "SW}7}cAm7~3R9cx37G37e$ce}-h6!j0q#P$6b`<H<eU3t0gsyLk<)fhKU)di-D4#>Xl!!7%H(LNr^VeUezAHkFVz!}K!mT@o*scGyD!#Mmss31"
    "^1a|y(b8TU?o7w*A_LE&`;mT-T&ekMpPKvdn_CR#E)EjJ<G0vpLb;3k4drwcYBZFiLEZA993GrGM2ClIxX01c0iMwj%<UV15Yz0AT17GX6u)sG"
    "SP2<Hyn_&->3Ep`DD_qaK*RovkAIR52zmVJ2R^Jr^$?Ci3Z$!XB<0S1G=|>MTaM}6A<Qik8`Qa3Nowruq|oox8*HOG_QgE2s>XHIC+c539b}K>"
    "du>iTds057B~P;-=+o@^b()8L`uy?g=7;UakAGY6iJkG`A3qL!g7i)e=^gxs6G3{~O?@#6oDMoLzm4D>i(7_*Koa`tFL%^nn>6pDzJpV6xrh&R"
    "Yad6C1bp_3{ot|*t#by>3@p4a&BuE*eoTBb3&X+SCH5u=`TUHccX}ikXF7QjuW51>X}>qI<8xm;6#Us(vhy-UcwA2mOTKqxKFQZEi1wNM@+r#G"
    "qP!D?dxNa3WdgreBrqESE(Zw;!QdiMVe)Y&i4O-8Rq4I%1(9vhWTkhNK+*}m5JRlcReCqe38u?j470FV8R!^I41!rdAZ)uj9_x~Fi=3r$HO8L%"
    "A9(@C;N54Eo>%EZl7&}^cu(+%+#)E%k6xP5{{5#8RM!tHP(63wjjN|1_D>tcPER_04C_LTi-fRY1azu+Huu`rH|+>0T8(Ex4>Wl6{&3Racy{_4"
    "6g=NUJe%*H29~BWlT*(S2wzzM);d9d(8%mwW5355Tu!eS<@*<ah%4Rt15qviyfLl7$2?6;n`LI6mZSOh>f^sCeAU*@vj{i+Xisi~?(UN+<}`=X"
    "j~>yhcK4|kCh*s}o*w180j?$!W*+%tFSum{Be*|o-oL*F{v`UvJJAEofm*5a&{k!gIihLUjTSfBUuejj_en-TZPtt=El=RO`%iD){j=i=GJAL`"
    "K1Nn2_6cAEWYz$+s#)t71RySq(FjV`c1Z`xhuB2|+RDzym?h@g>43Gug7)x9><Wwo&iVtGD*$+u@`Qmb+IH#Qpkd%^@%%(#^z+de)U_r`hRGMp"
    "g~=hl$`1BSMpDIMTXap<JE1R^DDZ33FNLwh0#G5)pOk}q6lv3#n;6Ta^!1r$`0;l+!vGOD#Xg%ta3Q70$#Q0nVkmsH@ouRz_ViO=|DJ@xrkcKa"
    "*D4vUvR5boZ$S$Nawi*SS&I6;5xarmmsi?$BnmIkX;*mEMVe0F$zyAaDCUGKD=BuC#B<5+Rb+JR5d+glo*mO!q|883>@D;FC1xHHz_7^XxdT0K"
    "9$n0Q2oWD*lMf|uzI&BThwTtmVQTr0@2>y48^+#98X!RWup+zNBo02kcn+UBHwK6z{@mq90<{7$ax}37Vv=W5c&AR|wr|fB2D$97Xq$v^O}pWN"
    "4WNIkT66sNo9nBe-kg1_;4%AGNg~TlEPo%by)0oYpbIeblp~kRcn4TqlOUa-SpoV#;PgB_j95M&P6b50<)IR+GMNeWL8cV=iYrNQ-dvKkmgPH#"
    "jRcXG1f>kPZ${j3up0cNdoiC*n$%l=Yy>&?4y2v!X?Va3m97NA-gq<e_R?pV4W#m_%@3nS(_=#$T>YryxK5xKR5t-{isId|*2k=%R<>Tw`ziJ>"
    "Icg)h`8Fm$u$ZX?lXSF;%`jSVb6mATvfnK4A^d_o0<x6E+_Vb(d#!nqXie!#1tzwXZ!h%c1vyi?`U7H{!)L%)0?bZF49;e)mc7F+i5Di~{4IPX"
    "#d~0LMO|7^nUGcIJb;j3o1Ph+?$&St1}_qTs->_!_<yL9J%sCB=S_tEvT*w(`RTD%g3VeYz)Vk_02fB^*NKfC^f)3xrCxgUcyceqnsn6keMhAs"
    "P%aXwW#Wy%<RW0w$-NyFgV&ij1pEWj3>yJH`CwAF=EjDw=m-HTFq~X{Wv&y0YTL^uos-JK8y%9gGd~;jEdFVL$*$y`)FTSs9OB8%kQT^|D;qmX"
    "q4Qal%@(2B?6P_k^ETJ+CAE=aX=q08S~9mJSEmo771jcp!UDe&&oA67*`^eGRvNP|{HbTzO36;SU7LrSZ@)}kC@-6DAO6tdR#?tcnZ}ok<k-4X"
    "RN0eYu~k%{r{d}8OhSWYGX*`xd>Qn4M5eYHy=Z24&*J=az!{#I!Zh5`xYKcsL#MpDMN|jH01NmYesMS)gHB@!VsZ|^?ce0^tq_J)xG*lC8+z|X"
    "6E%B?_Y5S;ZU|A+Aqv^{mhcuks{s_S^~FQ;G`X2EEOB{Js_Qa-EAy#ey}=-WqC%j_Grc~c5(Q-<6)Lf2Bcgzhfx7IrSGY4y9eY~2R=bTooCizJ"
    "R(ueq#+`eEf2=0m%;M|a-(P;Kfy3zFI_wnU2^)vzuxbKklS<q}R@oL1tZ>`W#uZ61J{3`@oipbXQEbf@d<I94%UY`59ncY`ZL({FACSrsLI#n@"
    "g8|wCx&^+#o~Eqjhuc?J5VZLGeuo{&3pY;N!CTB8Jcdvgj{nPH^y04bFD)-&b&1cp#n}S*Eq3`RxdE%q0|hI<y7l>!>xMh&zADljeDOel^hG<J"
    "eJ*(DoITz`ok#$7pL|Jn(K%Bf)u`BqYX*^JB!}e|?og%#D2u})>)@8vUcoUUC<>{?)i*u~C<wOi)IC~h1IB2%$a^8FxB;S1%f+;+UmPVP?*CSG"
    "w@^<Z4%1L>GZjy?kTBH2W^xG@#Z%B@7BP=&*6miL<vIy-myWkiPE9y(g7HMdXeD|IGe(Nv<E;tWuM9m^q|yAe<RNAktxY(Y)lkUK;q+;3C}|RE"
    "i96<G^RrIHl&xFoOvTlbK>|Tm0$~UDBZF7OOohifM_6=m`LX~O_h=fR0~ZY_D&qk%)}jj=cT7sn9~FcI)K!m^iOye5HFRihsKm|1h+UsrV$Wry"
    "&G<UQQ<^Xx21j1rQ{3mUWvd0@xqIHmZn>zz8289~xp=~h7Qu@!lQ@Z7Q~{$UkRxUgcVv@LL6H1=@Dr0{z{0e7v*t=M4z8#)nTWT6pd`XSp<qDL"
    "L`x>iL>w^u`=qa2MO-iW$6AainhKE?Li?4<pDc&LmjbOl^#yOMrWC5ARd5(!tO$UYRK5tP8~H`F&e(2iklTTSuuZ&Z>z#8DL|?VSa%?*|F<wa1"
    "f}aw$&`Kng>r$QY<H^9f!*Jq>btqmr!W-;y#L<OV<HVAdBKMC;-ZkhOArv(G$e8}r%92K`j)Rx`ZjUHigpualn6hZ%PAh<dR|dnHLj?}gZ4Qvq"
    "2;aj^OF4@xb%b>tTwvLt#vLyu=H-;oMh$g^geijf6E81lqaIFb!eTRVCKF$I{U}w%bdnHnAv|xBaC&7FRkeo{-!HJ6N)X?!N8B1zaF<pf%1D2z"
    "*(4qClYlwLGSsQPt)MG43l&Q*YUtT|DQ}ibx1}#1C7$Mw{PTwgr`4H2HDjrlCqmdx%*|Sm%@NEHlW**?EDJ|5KG7J`CQ`8?piO6&RV`HNh7F69"
    "Rqp5#gG;-YBjGg=ERP92t6*uG4&{uV7u~a&LKKeq=BhxYyie4ea4V>mbTC=x*>w}DqBipL@OTP&VH?f4v*-;)tcx^Zo-oJNqSVojpd2re!Zubq"
    "gmeDviG!tYn(@^@Z3yD>!o6@J>`F&-xRYkN9wT+X0rwxG6bSb_2ST4~ltMB$3AY-WFQar+G7IVu^+Lpqz=)PU!fL=a&5DA8a^pE>kfV9r@HuWW"
    "Xwwlh(AKGsT8A{gtpw8~jP_~Kc*ep4HMvUw%mC01t}*-)w@ME}=&=hcOdJSzmz&YLoBp5BPkGU0&xL1Qg2F>s?3fCAz6`g_Q*rVOs(WUZ@#r~Q"
    "l>A<}WC?qu1nd`Bg$zyKX4$@T7bvYXOP*F%PK_dOC6&Wr&vMvpKlSVFfyFv3{syiTapMCDRvQ^E9ClR;#`3BJ!q*R#SS*Sn0APl2vesgU<&?^@"
    "hS8w$6w(MeOO|c9BvzQic&VsMtamTul%w4v2N4REb(yY*Lni#c#FpC?NA))}xz#vjmE1fm#Kstl;DW;&)nuryWVyC~3=&7+pT0$arTVOP9Jy3}"
    "WiFL3GdUsP;u0>m#u2Au&<xUv@Hw?A53sFH@P`aH9b3Vo43Gr#raYFh0x%93T2P@<qOxCQS7*e$QsG)Uwv=R5@i=A$!nN^bo<Rw8qoz@`*cWZS"
    "%rOMVA_r}Vr}G>`8?gnq&fm10G}6k7!457;dfWw1&v#krS`x;jGT^%zx@~8)<`jwI<+wy~zZi&tm1)b9jnyAkmdMc~6pcPWSz?3~L4_Xao8I&L"
    "S%o%=q681-1lhUjSkfP=eWE$+E4W=|MKQsNcx#Tlt?rGdV);)1L{gDIcT5^qn~IY%H<CaCw|`3)NKhBwMy<M7^`3C+kmy%t5Y{>XoX&+ZPEj_I"
    "!C}&CoqGgRJrg)uPt4F1j})ePt58S=_(fTFFKpM0)&@n&nkrtg5v5|uP(U11Nvb15hr=e1>H)~HyIK$5+@7j;wnuXIUYf=A)?L9S*TQRphZqIM"
    "!{GF|{9Sg7AXz83))%073sUNa5U?-F-Opsnj4I*ZU~%oF6*#lo>X-=TEU36<gSEqus*dqyB?t<Jqv&M^N}TPEt{eY)FyS`_a9{RXEmecfqg@NK"
    "k#4b}+Zt%#2^S7P<hr3hfkqDvG~yJhHtn5%ee(b)N7E0Fh0CsyRi1;yWAy%<STFuA-mv+$KH~%tprQ*5wO9yLQk$j9wo+pwy#$>&-mx`AOe)$B"
    "9wg`lj#R+I$_~4&_jZ7u<n?_OuPr1!Gzk_jI1OUEE@GE`r_psJ5a={~#SK8oaO<vGn%q%$XrRoyvI>+W@oW%9X%Jsh$>WAJm7(~mwvC-R1Ka{8"
    "9g!)pL_>>)-7)?Px9eQpuTKCg+DA*RZ*^0u1@%;l6&Xusk~j3BeL~S^99}TwhF>*an#JR8Pc{n435u`*vm-cSBu1CWoH*{^MxQBWTZl|-fJMEu"
    "$GLR9Hdz;=aztvl&rmQL&GL#!BQtXdYhkV^n;)PO+r}^O+SC{_%iZ_N8eTd#SpttRGne|zP?tGWKIX2G;jC#iIL0&*X6AG@P$mlp2-EXE9o%CQ"
    "ybYG4e{ArRZ0Pi`iAp+(cDU38RLcJ^ijzy|_!LCS6>;CNfmM=;Pkf+ybTgbl2X2&tyI2cdL~vspdN^)k6{Y@Sef#C@o<s*7$;c)@KRvt;g3keB"
    "3qUZ!6g`~q!KFtoDp|cp4J`^o><-ozC&}S!doh2NqYhmc<T#_qIxQ4>I~iJwVo}kXX^VlTELh<bk2JZZbWFNw4Nz`qpYXV^04+LdEAt68B4b=@"
    "tAc+C@OP9h!ENfoV>ur%7O1Ej%3Z>4o?clgyVaQivc!88X6iIoIZ@rp_}xX??@I&V;}e7_3q?11s%NGPJYKnW^3#LooqyC5D?`PD9yuB0MRa|m"
    "TqTRyB-HI}5iobQ;Q9=e=I}^q10wNPT^yrB&X9E@k35i`*hLQ#-r-8Ju0nb4JLR-64+L*Uct*j+DZ5N*6sS?iF=>7v@+%q*y!i?w)FWCjg_iMd"
    "HGGb!A+pJ~hGh&w7**%zK-Ps+j$@7rqq~9$<^;hh#Ge?c#`ntV7BpI1>qa&5;&I3@F|P*%1mPQmWJSmQFkI|ga}><8vn83+lj?O#s!S8UNJHop"
    "IGv}-?pLlc{fJmc0cA+c(0J61YRV?!YI3f9mz~w)|LTl5mNrzttK-KZYdi`>P#s}OG{_hwR06AVn+SQPF3{1+$FWBTib8KKu|?fs_8xIl9s71|"
    "pZewedURbP9ZZo-b9<&SNLdo3p?1)9L>&}(wx^isTdkKymjn*^GOwJlut^~_j)({yQ)rwKe~Q1RG~QG%dB_gbkxlnAI)YEw(VxT4h=WIu#Lh^-"
    "j&!_8HOC&j-yd9(H$)RpSxsHoQQF!l^mfg|HYX;PM7geLK}BB~4ANQ>*&rAn#9tG@5;CG%2&r-IU!$cL{T|*R>uLIFup5!KrI|m`M63@VRHQ;7"
    "q7h_>x|Kd4BQVyO#!1n&US$=oRFW*J{3ID49fN@Y@)*tgsT_$RSKQnvf`e!|x(K<6GO)n(jc3M6rbg<)GYSSi&f!@HoONfvBk<K~EpQGTn2KiZ"
    "0WpcP5()@m01rqG(DavJLQ?xlvl~L)z)OMEz>3=kCK+4|fsx_31|V!`MLit}O~qr&8r*;pLcVdt&-wOug4J;XTbf3h`b|?eIP{mt>bI0#5Yx~}"
    "b?>r*wr~YJAI4dZP?fcWs=T~k&DG_T=BlQ-;)IDmgv}33;(dSx@-5gsNOAHzlt)V4t>6})T`mNMKqpB8`NCt-Ad_2xAGP6NoO%?wyBtm_C#A<F"
    "stn9=5++H>jmo`NW9py<=pqy#VL~f@Sr{RJtt7G#pyZqwiU-6slKLlwkzM$(M}}gKsZ1M|x61hP%3y3@fnKqIk|jcHE*NYaE=7+3I3>|N9EY$)"
    "J|tqh$4YQ{HXN}IgMc4mHLuAARg$(+D%cpH7*yb-Sc9L$^$<qj8#ky-&+9iPhjzf@MT8at3@ldglxTD%G!Nr7K?2PX)g1K1%B{2ek-CDcWobaz"
    "aks1iYb9x}&dL^tj#I0(>mr;Wq5(W)-!I~@pA#wy8ng2OW*VuxXYsRwBR1VTAzbvLiI%fIqTlT5%UkfsD|LVLUzhgy8DsHWJh6C|_Lo+Tf*!Qh"
    "kAarjezVeLJd2k!)BLFE>V*l7&;D7&gIb2kD6>T^nVk{{>(&dDrlWv`p{%5$3cK;ms4ZP0Y8hBtRNm5GTMfKU)Hd5h&an=$6G61;m6#lQgzJbR"
    "jN3tM%M}iV(kQ}h;a&C{MN&xnW%`#;A0^-x5+w4}=&o;~S5qJxuG0#ESA?%(6ib%HiX*VDYW|k1w2g=wo;&-Q`*uhneN#`9BnIl-1~-4iA{w%c"
    "1=zxVm^na#+eO`hxNa%5^H!a)*C`)dHb)_Yi^5w?M&IkA6>jJ<MxDE&(?vQl*1G4n<}%|b<C2w#eFTSfW-~NHv6YYQ#qr-T0BZkzbAuZUDFHaa"
    "ih;sOyht5}kksp44gg38y|>*OVKqPSbxlx6&8C>U5n7UojwEIV9D#0pAn_D68~3JJ@pOCVqEIpIs=eDE)>Y}10=Ib<+;^{I=B`hm6uVd3fH}G7"
    "#OiTkb*%Wr<HG9D;gKMTtsWCr2X#fKt`DbM1JNM=W}8dn+QfHCp*W{JT$HPyvRK>=VQ6R`=8F8WzdW2wR11Zumi#1FmL8r5Qe}!}wCJK%(9HEz"
    "h{H&&z0xFjTP%;wk8XsG#3UagfwI|bz;_z0+b!5m+oo8&nrGKE<LMxp@v7ov^=mjn$dF5xU0aR#{RF@h5zB-sD@KrM0;rVbB~j7XYa7NJ3<GN_"
    ";l`C5L;{N^P=w{^;k(2{d0aj(BNgS!)JmxeQ;C)_QOP>h;3mZJ0n#%cSB-vC2DhY%MW4(?lE=+QsE))jS^yV`j&5djgpWfAXbqLIOTkvu!02v@"
    "BH<^uJZc55{Ofz}g2ft*-dLrM49$sBZ!WZ<CxB_!jGP>OyCpncdJn#Ep8NtpZ5xg%-k-v9^Q5p`q^h0z$M<V?-d)pfaeu4R6u4v7Gn}8aRjqak"
    "*<we}nAB~+32SNpbeUb4clm_i;{XgNo+-sLeexV}RJw{8i9AeAKt;KiR_nwMfojfR2Nc=mvhrlnCUF>mL*iXo*9Yo+`P%oGsl|3*vxLYBULreU"
    "mI9TkBobA`rMU&&r1V`NgwB*t4a*byB=MeUx=~!_5(>OvErz#Hi1A^LT8TWV8GC_F_UvO_V;jMUG8Wh2IxgONAikvNJ_Z^-<dL-<@SBQ;mROUK"
    "Omkz-lp&ZiqSb{*2f5;R0jbbw2>@MG^%_kI&_uHrLfk$ES+Ouc1WG9TZ>V)1zm<**Gg@&iuu=^SD^2nX97(QA+81I*cW>|Wg;bPB?5tN*H+kEX"
    "mrv&APqN5Hs@3MvQ>`d0y@c;?H`gjCP15glK0vl2R$5E3dcxrji>__U&Sv4gWmOA_49iSL!mrh(YGC1-A@75NiJV+dE<^JvTFz~<axX$g+K1^}"
    "iYJ?F72qnVNY*@;wHupS%2DBS%l?)MP+3JLYjxtLe!#6vDz)Yti$|G?$Dg3s_G0WSyO8wKeOfX@%11Qy%ARau?LNMTWd_CIEUhyfIR<~wGU(ox"
    "aWC<kgmeJ@WY<Mf)1ovmN4MGxsRAKfWw}t1hgIO<B?$vTCYkOb;kPI>sNg!35wV9Pk3v7-L`^;6&{obHaIhyL#c#L9usT6AohPU_D4>w{)w%=_"
    "MgzGK)Wb6!0jwi#w`-S#TVS=9(70OH`|U*@R1JCKSIe0GZZ6y9m>MtKcPTl{SJnl_>Q>Ks!MaPTO16jYG5ajN5*CN|W&{811X{#XB7U1ws73G3"
    "2rUlIUYuY;+aN%_b{++MhVtzf#kto&KcJ|SL~HG4Xd(lxXz<)vLO>`-oLDUq)lKK~%n*wnPb<Pv(DZ%PxgwBrofKk09nE-%-vutgpMqN1NEr*#"
    "Y?_~QTj>ZE?O9-U6^-CM%1`RsgOI^=E6f{-Ar|N2u0wsmHnt9G45leo>{H|=i{j@5$3?BQavm@zi5j_b;P)-z2Y#cFlo$>W5SYXjwbC_7j!Bxm"
    "NW$w0BUomtXl278y_jTTw^d-ij43`qcM=GwKRuTTa$mai;*DmapXkV?J}rQ=1#kjR<O}|vw4Ivf1*|ext0pWrx<Y;Qt!ZvpXFTc^G7UI#c-x%;"
    "+~rk5$9&v}%vTcj$qdPX#MIi@vAYEtVQ64k$G!u&HCVgJOOiB~u6+)BX?AOl(=A<vU|5rR@ubPTS54-Fu0F7cC{wqCc}%)Y-C%#j7ylk)nbfYm"
    "X6;k04v9xr;CzV$7#MnV*rlbbUw~I6nHspY?x$QN1F))?A_y$hdG0S(N@#tWY&(dAN?OO{f@2~zyq0v`Z;%=nsz}-qpTg-xyMjcK>aECq^vf1r"
    "9P@@tA)^}QC5$Q=DT<b+<*tLG5VeO-iKNvInUVklx`RYmZeh6gTcioRQC#BrML{Qhn62d-$=Q}(T^it^xz!4>Ha55i6eqPP>Fk_QZj~5t;uo2L"
    "lqT@zI`%Tl=`JNu+k*I{U6Q0&uObDN{}de^ZJWl&BKNrVxv{B&Wnr~68j`R4^jtyKn0FYolcNi2`U}fGbKzyRGU<Kr#a=2^ES{vC4-;70pB!Vv"
    "t^k4(D>W_;GC}C*2pr6d#3&bh5uGN5H}l24!WdIva5aD`93n#X?PRSQRf5%htHo(bK#M6&XrLPAB+3p@Pc}+pKp(*yU?8>-q{nb0o^etScV|ZG"
    "bRlug5%wi@3K0u-E!BPj>IskVD7Pje%$w~JHh$<BihRphDjjY+cGpRIL9M$4EmOv?nW$5WB3n|8R;6RGYH)?Nfrb!?72zUL0@)Dipjezmg#ZbF"
    "QmF-+%GCt)ZAz-5Vy4__DOrG06b?l>s=yWn+z1WXpq^-h*TNZDEc3FW<(j}By4YfghfjzouI*If?WNZGFq4;a1mu+uw}KIYNU@19uX5WoyDo4a"
    "Hd`1eJZ@GzQ8f}H+R_}X#Z`tULU-2BBu>#Fy3=@tdU+zw&7(kf20<P8Lu|C^#Q;@wXS|zHketZ5b$fH>sWjdt8&BHnb2T#4O+>|AQuI4g5@^_`"
    "K3A)C@m!!`u4M?|{xI$jb-h?d9jTUMr`QP0NNQso&9V?>aZ7j->Ysw`LJ?zTy5W6DC8&fKqn2pQ?Eg-mWqJKp4*USS04YTVNdcInsvWVp&*)GO"
    "(pPMQG8Rk~^`5XcXrU%a$wINu8fsB0-h_x+$E*(@t7bfbDRbUBZ>c6MiI)5_%nA`%%uCW0tqfO~srA5IZA|yjMj|H-xCOuC%~cjHGX*^W<05{D"
    "UQl5!bBZKcRTl<JccCs*tWut3?8I@nwSfY*S3V)rSutQ$NaI;6MrZm!UDjBgJ#<7{N|9QVbDTsoKdNKm%yR>+c%}7#vDk*HrMx^EQuTO%j3SBb"
    "V?j8iJXA!cY1@<mAav${)kW#`r3*JNXu=_>WYm{w5sUuRlFgK=sHZD%s^aJ}sLmW-_2uyEy_|Nd86((RXnS^3L&Y5`95+q5fbg9>?Yj;@^|3pr"
    "U{uNOufoE;taS<uVO=Fbb6j^oEJ${V%Va{q%U~0~JnfUfFbp?!q#5=n52F?KC({S6va1<aTB>icZE3TZV`oaep=5HDhR*&^>lhLOHTjA6S7Fm$"
    "4eiX{548>P)P|=voT?4q{vTXbWZV"
)
_V10_SCHEDULE = json.loads(
    zlib.decompress(base64.b85decode(_V10_SCHEDULE_B85)).decode()
)

# Current radiant-allomancer trajectory from episode 89474114.  Unlike the
# v10 family it front-loads a cheaper 3/1 livestock opening and proved more
# robust from player 0 in both the current train and chronological holdout.
_V11_RADIANT_SCHEDULE_B85 = (
    "c-rk<%WfP=lKdB*dFZO5q~+e&QcX)3wkVL)6lNMiqk)~p0*l#0&)gRK@2hTBWo2fVo11%h@}aI<q4>ynWrVwhnfXuud-k8d{Q8f-|9bZCKb?KLy1P63a(?z-"
    "zx>aC{PXJ<UqAlimtX(;@BjMx`KPn@A8xl_e>(c`{pY{_eD(3ek5|`c=Vxzkc4z0S!`FA)?YpmE{<yuq`FM8zdiM41{r2kqx39na-}$%!-+%sa{qE<l&A9*k"
    "`y+;y{B*Y4-rfKH(2qB__wUcXOxyO`|NeA)^X~K8`|-bzHFp1JujZ}#^x^HFKYtqi)u>tf)|`(&Jv3El;M!`}yaCr&Z@2rOPM$s=FRvAM+w1G&<A?qW4ZC~4"
    "-F`w%JB-coFGuaWyZO9tP21AhH@Svxj#E5q*q?rz(@A5d)3~0F*7j<@yn2Ss9-U$M#tnLV)lAy{4Lp3v&fcsUhyM@P?bpTi@qTz!QFB-;*7{(8R!kT6*TKKK"
    "-`<AXAgtr*c4WR_57UGvY1n{{i@J1p+66m$5Sb&mAEuYezPsqP8FvXy)V{g7;b<DNA8xp0hp8AopqbE~a~Rr(pHCjRpAj_t=7jLx&-=I^ML6fjAs&5FPnL~8"
    "ob4daKCrHA0>e0e$(7NZ{kv3;+rb?s6prn~r%<okQEj&ida}T-Tm%O9_y#m%I6RmR=Cp?w!YCe>$uM^F1{$NO^%k5HVDIHGh0`m(T4!BpziBsSeVs}p43=lp"
    "^H_&Tm?ky)yovwa<BLb^;9%en;F0F=-o3rKzTUpQ|M^eb+xrjKAO1F3B%$<S)7vI+VA<({dXgtc#Tg#0HObz)&m3AeY*`?dh;<x4a<&(%p?4&les_EGDe;J5"
    "qDL)m0|xMt9rxhFKS%pBdvH2>pG99JFzb4<)M@hs3eD_cljWV9ojf(YM2~KJFnUiD-6KI@vUi!O>g&V)6~<{&+X?W){2a~kG1!CS6QyUnk2r>LOFe;hA~Q!y"
    "CyxKO{n_*EL;pI<JYpD~l3{B9N!S0Eqsn=BdTyL|<zc2A&Wb?Mf<dT`96g7)R76+4sqmCyT@~>um=6W(avr_%a332DNruA&m7puFE5NV;GY2jR^hf#du#r|r"
    "x&#S`O&5!CkNHtMf*kfP2y%yqqX2PsI)#GVW6MGRz!gwp6{1J9OHY478|4mvdrUCf|4SZVAGq1r7sPbdT6v~HBMYr-V#Z;zvcWr?HeqsR|8jw>;VGW*oPyQW"
    "69%iNsPq(-f~eFDZTdh{7L>*VVk0UA#~b>Df-D6=m0--}VpImRRfXI(7#qJXkA<l8mhKyfP$`5N=pYMG!3wDkQQ1vFpcf=YWdR$FQ5TIx_0dblqO}h=#iFNJ"
    ")C@d9jCzViPqC=S3|u@IEsKN${Zt5Soe=5!tJ}YLp8+o?gDj$*%jcF)?=3c%*}m~N1*>xdbxvboxdD$&vqDhu@bu$XL*vY`xVyi-+I_#hz5Q!T1lC!nFf`gX"
    "b@T)y&IZ3|w%3eyY_b}92imwewn!P{Z~UJ|3t@X_G3A`)nv24Xr_6gA=rSS4lE=2+fbofqG~*hgl^D5^YU6c^y@O1vO}Yc*4D<iBA9|nA*9mqlU(*Q^{kQZn"
    "5YlGpW3jZx{HiRkk-Am{<8D^ZmvrFCzaA~5mV{Pj>vI~h<zns4La}yx&et<{1F?52txJqmcF_&5x6w?d0EDeeWNXK*axT<Fz@ett>}<eM@8@tV16!+>vY3c<"
    "63vdWA^N(=(-B)NSlz+nqGb}zqAt!k@8=GwTkaSLqCw1F)v-2)9_x=L>dGK(HZ+<;rZ~)8h_=~#D?wwMiu(z6|H4|4>N3a}$Tc14@uTulXiHq!wu(mkgb!MX"
    "7~DeN%abl%KXI`Bx)(u)s%Z%&h1mWwFn1Tm8p(XJp|2B&gVVVeb_PgeAQbnX&SdT5U<Y)KKfUHK0o~s<O`=lNNOT2IHaCsvxN0Fg11B-)NFoaoY~<Y2-fOeT"
    "uxoUc;HJ55Z^?kt&Jszyj?4n0twj<^jV6<2Q<BmQ!oz#}&CNAC<sxrUn<JR0UONyjcmp2IKtq&H=yphf%@V|Tb}ADBW|#?88)6Efe`fhnnIl3ODB(e{W>H=M"
    "hUJ<+D`H`Vlxvy(_C7N&`)KF7rRua71oXjRQ`xk%k=2)l!}V29?D~uYd5-f5LH(-*gZemYIWexUx|ua75V0uD{SfUD7jmgA9iV^U{Gvo|b3}@xe6O#`pZj;w"
    ")ItM9<&bboZrbxH0lkh2QK}=H27b3MQN%ma1UG<As@Np5IOREa(UEss6M*KdiUNu<yEXxdGzwxB@HFyxn=}$uD^{#E#xpp!YZmTg$g#;pInR>Lj*Sw+i+Ha)"
    "223AN@bq+;&mI(FTz9y(W}Btp;~mW+dW#p*s5W<rJ7S$z*zsm)_aJ|I{Vda)eVeYYKEA8Sbs(p*JjL-zMdv2DcO|l&#k^@)r3vPZX3P8IhwDGH)$^t|S7mAG"
    "Y)TdSmAhA@r_La%r^!<A3Wafy>?@=$yInCE_1IIxQcR?$?P8#7u{(>GvZOY#4ZvnKd_$mQ(2<h%2G{u8S;|qb3<7ZQ#Gso>Son=k+u@q{wv7x_VS()k6P6Z$"
    "x&TdfI4lv|EN&xx_<dU6Kxk+iSs^l7Bbs41xB<XV-H%~m10dXiH$+rFar_H#TuGuIVMrCGu?NbS9r8wX?YFNTB9ShQkHq<OFgVpNiGW6fo}>02X?8BVFd3j{"
    "$hNqcA3#wvQmQrOZe;~zwQ6gdKtrHF(7Nf>1Lw$A&LK>MDIn-Ap_nly6I{n~tPjE-@}x2rB5ex#WHW(tRKD<Y!C%(R4DF}Zn83V5GyPFYHdC2jux!=ceKd-i"
    "6;pi|$&_JDtEmXKf*r`iO;LwFALTbu;ZdD_YIHu(t6unJ0}z4#Mt&!=C@y>Ng*i3VqFP2Ru;MsE<*cDb9FuKw-&{|!<o#$73D_SH)idy^@D4jX4XC;r2AuTa"
    "ueb*HP=Wmer{e>_0^>K`7lcw+b8@p|IM2)@rVTbr-u2NX^Xjw#<3iCadwU7*>49E(k-r&O88KZu;%&Ryw`@8C^yMTB%^z-V?zX|Kww+@Sas){Um^2x++oS|c"
    "ZWXO&P)%RB9AiMI3q5SZZ*S(Z{Uc%T!w-+)4~^a#^hQmGt&Oc`QM*-Ete6cj*LG425P~+MM<j=q6%dKB2f%SL>@36UYqVQPfs&Sj$H=ci7ltQT%fdCineR2r"
    "DHoXK26ucvQuBX%7kiDp5f{Kqd4+$IbZ(iyIgRS}VcqGVhXtr;UPgV)c5pGqxKhlGC4-!RSEfC8$V<eQNCz7}%gSDDo)Ef-Jp1|J5UW*=weWa|1I}_O{2rLK"
    "x=wPqLAZ>J8y$M{?_-%g(?$(OhS6{`;hpufypQ6Qge!OfZ(ufrxur=+!30HIUnaxPk{^<ICY#xgew$x<z#KTUVpAAiU#md<7NW03sl8kkDY$M3OOYoN^b%d_"
    "lMnW==#JBC1c!Xf`hy1Zxtv+Hpd`MO9{A%okcqqrpkcvfoT5J}`+CUoGm3a}>&rv~DA6ZZ!re{<Ot!A-_C3)7UK3qXbdZ!&&m~qQnDi$(lzhSf0k9=e^JJN6"
    "VGm^v$F%B)o6wD+=nPs26a0}mP7WV10V|PI{hM}Ox*w2>kO03)k&j>*kWx(8BgD7fu2rViE^qs_j>tfOuOO58o8p)_{Go$!np6W(wOXq{tpnh?Vm9sUO{2a>"
    "1?m*Qw-fAEy`MG9+Po;jq63AZf)gXD$!trBz%E712{!-hi)N<<oRgJRbL`C%0y-Bj6VO?|BtVBbnRX&O>qkO%GKDI%bbU!WN#~N3jmntAL26oK-8}A;8W@DI"
    "k_5Ow5}JNoi=FavtJ;5}DLodb_=1}(K}Gmap(d)&ajjb{BzY_7d?wpDpkBO%$RO0G!oJ()VgegvUS=vRo{%7s<2YJ9pJ;S#&EnlQZrv&vy$uf~Q9L^1-1@`A"
    "Mhzfuj(Jp*AT-XATrh{)Ur_ItWjG!zE#{Sw2#Q31Yxu7;nJk?ij?H=81`5+s0fPux1Sg2<E<}9XU$Ew7N7X#h(orLv86my^nqamr{HP3q6oI*eJ#$=<=o+IH"
    "GpVb-xjRZku+|_^e|^G^GjV^%{33Mki2_$j;^dfirnx?OYfNp7X82jvjdf^=xkFEz#kf=8*B|y4&3;Lqq#iq#%Q0;BJKcL_0cnnUD0kkRz_gbKrg;jX=M1L_"
    "tQs1UMdyC`MF;}?wt5Rg&g$CFngY!rvM!?dmV=SKIt&NH@;2Wsh~Q-1$~ndL+(XCcQu5494R4z92UvAB;Q9)H3z<Pt!I?zX1s0(@7*csiM9fZ=0wqmgQx?FZ"
    "XXvjH?FPyDBfVG)_ra8FgSH(aYqJVMNAO|LL{DwNlR(gNs|+jH9g<9)cJHI33!rv5s4kS1i%+Qs59j5%yNH|IZaZ{Kj!&(ODN;I>ExS_L8=NLp3y5qZ&MyM7"
    "64Xl+5WDUzl>&1qn;ulMu;O)MYPy-4Oef^Biq5_SJIRIuygMDzi6SB#hp6;MR}r!pNSHf-8GhE|LL?T+l&rkMU|0ZB65%`_RP3qn5Ht1JTw43~rh%1`5YpxZ"
    "A${u*QXg~YWf8KL6xQ{jM??RZcB*~TmX@F~B*{l%fF(wd0#hT+Cj2cekHml%q$J7Mmv92dSyW;*M1|uQ!e;XI9u=h%s@W+TYOp$(X<uws7DcW~<T94p?wk8q"
    "@xTXMpimg-7_$R4kZ3a>tj!jfHSRk@OmfZ065ieSAPR<Kmr&`|&ACaWUj^j&#bTWz4Nh0*U&Yci2DlqD?QXD?(IStyQyggf!w+D8qKPPfi|Np^l)q@@FwR#z"
    "xu;EUNk~;H=QaVI8&7#@=AmsKJSY<yGBu9{V;U~CGQk;AZ%#)nXmv2Ha&u#EM%Ad48?*rXO6OteWYxCJa-b}q(j%%drE3cj{}@K<BCM=L)DaY66v1wG6ZL_n"
    "Ypn&hZ45lgF3TD+y;?-qM@a>b3ng*DB<@o51mKa54n=Sa2a+P@5|4`|sq<!C3+pgNSmM{;56y51a9mUw87m#t-+ab$5lgN>;3dRvp_O}+&<MZcPgG}$7$u}~"
    "U51N-IdP1@vd&D2%Fax@#_SK>>5%c%JQzt`uEE?;1ra_pXY*QPa7;KVfFu&JPjj4byYhLe6JqP%;~^v@n(N3-cMC)?6%0vjm_1R>A`6rGIKh&#KQs^_ux-e0"
    "bIi3HEFE`0a_^Afe+Z`zl*C1mp1^e%qmO`nmt}OKT2EpzJ)~|n9;{b=62*TBSOY9=g485<S^h?18!u(DQ5WqN0iA<YSEK`!0!K4u5#S^^K|2pqEI{MUWqKX8"
    "K4Jj7)MvkK6vu9XB?Mt?Rh(+(50}~r&V4%-j}1-$Z_;7DBUnapm7Jl6p}Ev|l<yq>re@g_F46dIVtpbIy?g?Z^N-98=Oqz{^!(hhDYcoqm6Ipw&m?8aJYVkj"
    "GD?t!Kn6MUqLuwxi)3dqY!<`<eOgh6)~pS7b=gn5YD8xsO_7#!y_FJ4iSdWt)haJ6Ruq>wUC}Ez_|jXI&HE~I9G9V^z6x@}BF^IH<OaItP2dJE+pOCPa9HbD"
    "@4%MFd%bXZETyDg5-3*z23lZStOK2VLpOn<T_Pamod*CfhujobcgwU#ii*@*8_J&+*F_U$u<Cabmovgh6QwK+lBdjulypcmw&LFJbVRB7dx?>Ang~TlIA>qa"
    "1WpWE7uhRq2gTa%*(QT&96*zn+6G9s^nhz>%t6@T;)`CQ1kD<Nh?osF1#Gp-Zp+wWH`og27rAK59y&SMWIsbxg}V=zfhy02OOtW-QO!!|HvcrnKDt>nt4hqu"
    "+?3h;gzc|ELJ#K;9CU6{0}=(JN?eXz6Uav!R_{WL8b%+0QU;LSf#ntx95@C6nIg=DdJumVc*N4-txQ4<@cJ<`cvkYu4oNep1RHgoa|qX#F1944UpuCQaaqI?"
    "RFs7y7!VipvxuFL<n+Xdl^J>qEA)tfDP1V-N);2en?ei3<V&~}>vU<Jv+1;I!)_U+VOZw-rnr!MfN-Rxy~-7~IQ$j0qM36!IHy1wX=qTh+et*^0?<w{tbs7c"
    "DL<I!A5!TGwOrx|BLmYT6h9Fa<4#IqdC_eGwR1(fny^Pi^>SmllWuk>p@_nXG=-}-!!d1c6bxpJ`dlP@mV?BWXQXIylK60u@+U`OR9oaOK1&K9Uq69{YZ6}^"
    "eqmbh6dK8hfjM_&=_*+kS&td(9~Pj4m<3*m)>JJcm5?w<GoDn2+<>nrm{M8tJv&pxkw@`(sb&O-1<HL>9Wo~^Kw5LlDgk~xgbbNB^FIq^v}O?(NxDIaK!h~b"
    "0Rlp%46<Xwjy?d6LRP^pfRI@@Ek{YXP#@>vf))=N)R3bkm4P>tqDyL!hp<@-$)!(#9cwfMvFwq_w#a2kG7T%DNV58M)5QSxMNUls2yQ0TiD<ext%;jti@AKw"
    "hR<?VYQCqkfdU$_pwW{EYKd*nz%+m?L9<#3d!g>!H83Nkg)vx$LJB<CpF<VNEsc5>i~BFEZZ|_JvZOldOAOWvC9&E-Pu!%5!e8R30=TJlyf!&E^^&BOu5!GD"
    "gqR3qb0W!n<KD$Dgd`(CGD4)nH|x{^xhQRhaRC4lkRhFPEkfd+8z;)h?2L4Es8CfdUCpL(nPtF2;mv3T)Ty4$G3W4xB8O6tb%Gp<wZhp6TFEM!0lTOQaB}g5"
    "f_U*%l&+_`c-3eb6++LDBPjVHU=Ir5IghEs0ZPR`r-l+E0;TjTvE8+X){Z$fcOZ^>F{LVqO>q+Lq2rZZWX-HF)+bvdws2<3s`2)Y@64^=&_Fi!DpJ@?A}p$C"
    "O7SpLJfG1~MU_}ak}{nf^dKhs3k$;Zfz8&T*7?OzIbMWYLMcXUssXM=J?&K$py-H`a>oU221dm(ha1udiw81I&mw3H1G}iRl0-s&l$ufvTL#!tS>{JU0?l}w"
    "U!NRf{=kkgPt34+EX$ZsWc*w$W6bKX%R0tDVOfTg(d{ZA+|6aN8!@j6Ev*`oOq*|0Jz12fROT7XYd-5f4lJH#4yYNNL-LJDJKyk>x9T16uqVoXp~x7$8q^2^"
    "J=zpmPen_OMAF=f99=7JB>Gl(6__pIYqmzNxEyFvdsgnHi`@w_8AgDi90qsq@zl66Oq*~>n9DF<qqvD(ddXOM9LAwTNP}kW5yA76aiv3p7Q8d{6`KTG${dGb"
    "j7^TE@OuG=L$28agF_wysxU&JHpv}Jn8=h7XJ{KMxka~cpMbPs1(2LM0gDKZHj@-GgK&EM6L6=nI;6&@q4F~d)H=k>4q*kE^VOPTJX|&ft!p+pXu>qdsZ>@q"
    "1R~td%}HwY6jH0sE5H|^wX%Q3{s~QU9$Sp1l=#V9Ukk>cPaw!*;xIz{@Hhw{Wm#I91(K6MsWZcE#0mt96a~H|1@jb@e1KbZO=O9!19~jRWYRp7g=9R-J5w&1"
    "HMiajqB(jNyvr{beQr$VRGOwdkA&^ay1)3kZV2pIUr73<YKa*uV&n?P*o8aP+ARTOYDfu1!bMBzKDkA(TolaNDDF@zA_FMSHij`cMV~`e&nW9+XzGx*THF_k"
    "{`lq7SS5I#o~<LsMaQ<&b);dd+=n<rH39$wElLUCALjJV5wC5yI2ygKGvtsAPGe_o%0=8cADr{&=q=n}RmfXdVBxeJlrS2x&R2m0lp`l7n3ZdCjfaFGIP}h+"
    "JudfB8cQvRX0yx6)J^cCc6u;}r@&IVsWcAO!)pLey*??#{=f>cm%%j3fJ6fJ^vL|9$QoVF%cqQ;<g8Fd7Q{&~8Lm*eH~7@os(kNM4~0HBH^N3@;ELk<z$;o="
    "jHN|MVx&?O4|jbAK0xz|6gF1TdRWTM<&!Xi^m4_zX2H2b`WLNMq(a;a!WDiNg3ve#vXCs5Lf$N_u9mHk($FQ>ou|iwgHUSqs%TCIVlE&G@51Dssu8tX?WpvP"
    "z&6fT4zTt)8WzA2Wq?@c+R)TGG<Q2}lD3pqW_e@^xqDP3W|nx)C2EPw2+DAQ_Wt9gp@CAKj6QR?FrpHz$WB{IOZ+9OC5HG_?r5vFQr=716`Hg(E8VzG)qYYg"
    "54SzH0j{8)uI*<llyh!uMFfdm4Ae`}E_LDAq*7K3Ky_%*E>2psmqI(L!iQc60jUHRf<IZA_u_6SyF_s-&7p?EMBt6gl$H%O8+pJ|B7(yg63s~6$cmXBJNH0("
    "N&|ewHKkWgC0`~?13%MsUvaDC&U!upfe5=T-#T^aYNTpBSA|IeC@e;ShKP+*nO9QNSgq`@V9KS~`BYa{Vx_kofg}U2AakL(YP4K&o8|S~a5&_23lSCm7Etk{"
    "4Qz2=q7ME|P)`-F?`}XeJV%{#md{I27qG|h{y1*mVEGs;U+vFYvX|FQ!dg2Op4ln|;}ae*AQ@YC&8cE^Ch=}OQnS|k_`EW`opmpV+f8+iRH7^NC@@P5Fmh2j"
    "O(Y4n@cFuS&3zCbq-)whRYE4&vozmS%0B=)CMG?>J~p~PPhf%x&cwG86>z8eIZA*G&m-xJF;gnJ)Vt7(bSN-6VT^48pS9>CdQB{9-7DzIZA?TD^Qyag+WI8v"
    "TSU_LLM*wLtDfeeVIp89#TbPp#%!e8O*t5&tST{2bd4cDUed@7qS~+eij8QK;Htu8m0_yb*d_uj$OEm{-C=S8hryK5nK1L}mV$*KD@~4<xkqk87Dg^~?&fj4"
    "!c(Y9X<N*g9$eIu5&>S1O693Ecr{Iml`Cjfg;h-7lS<sPWyTAT=>@el+bVir&0bK3ZWhab3HpxLs)NG9^Vk)O)q$@Z;6zE0OS~}FT2}5hPDUd2G9!vS<+_FZ"
    "K3VyC^+NR%rH#==x!V?AL2!tbnm{v|I8*hBU}d|eqGh;Z){t^lb<i=U$C6RlskKv4_oye5x@$cAY5dwHRwfgv^Wf17;Jvnm2GSV7vB6%6Xtls<iU|F7)3w&Q"
    "o6;rIhd*6%{E5DtVWQWGzx7AqZ)J)kf6Mf(0GVU~2l6y~i`Iy%sti|6*HZaq9fmy}Os)vj<Uj=lOrj)#%Y$EOzvW2{5xD3AjpaT@0eDA>CW9M_^SEu0C33lR"
    "bzi60#!H#zNDK!e=_Ryp`7IUaDtGc`0t8wVhao5xs2PKdncz^!OU>;G-m;T78PaT+w++}^0E!@`B0Xl<LTv`ZDQmM#{A2G3=%U8N>YCH@HD3Zvb4ZT!3@p*5"
    "%VYEfu4+wmTbx`(J>WWCwRRqa$}IMityg*kdKN>DHPa@Fc}Wby!1QniAwLkni~*A*;ZUjJ3<f5UVJ&QbreKx{#>vLr4il}5jit>gT6+wNL>#ZmH?8f5eU5{{"
    "w)O?hls)9O{%CA0NBF1!WIn31j%y)b)j?;|3!3vs;A@?*v~QTYRqK%z*ETK#ov~zt8UY-9BY+C8ykH-}%>oW6G8ZIKx-X?BaJgbq2{wU8mVs)>*{>NzL0_y0"
    "x+xdwD<Gn@eGA!o31Y~c7nTxp#_I!!0lDjnq%W_FSV9+&&9-2K9os1|MKR70FV#sggenrStMQ0uvv&S>I4U@DAi8L)MqrD94IVqhQ>Snm^whj=vALmDp?qV%"
    "C>_a{UxpmS8Pn7HEJ6uzotgG}Mf1~Mi%{2p&iM&fr0oQQ*3o+sPH>}ef@)dkRA)_hjVgc1-2kOGqJ7>W=GOMg1CY5HBNf7mWhiU=!yFTL%8T%vI>Y$jvWL8M"
    "TQ?wIGb}PhZ`?!x$I#4SH#$eJ%=+7U)mQI?T@c--C9FB1ou!v71L`o>`J|!zMl_V)Y*oZAq|OPW9$i@J!6tE;<*uXT_kuD@ctdM?-nTeph?Q8zK+G}vR9s0A"
    "tkvlLGCEPP-k_S-6OI-wxwcaTK9*Ki&E$p1ez7{4T^@=w-j}Ia7hh7f&5(hT;u5H@$)!pVh$b>3^+8%SwGM5xv0Jy4nuDVhzqxJoFNPe5HpCif$q}&xc)L5#"
    "dC76S^Lcee%bsxmykyx!IH>XE0Wn@iWJ-(9xLYS`?qMy`PSa|10Ve^MfKNGabQO|uk0>u4TW>3CXPhaqz?~S3J|z6O?M%i^eb9z$4trdQtdgqwSc4TFCoj&U"
    "mS}WUlWj92{#GiB6Ks8l@lCW)6g7)KWVpTGxH3l9!&x;k(~@ccbePz$zDoc_Cl%x~XKp!o(o3aoX&jUD9%W&#Bfa)KnL;Gdv{Dtofo3jKWHC^mP>^NjGYviJ"
    "GYBW(OV4$s*R6gXNLLfeMhCBvowGYiGHUU#ezVU5jE)>UQo4l@{XBew$4a6lOb3h*AeKo`h-c(#qz^^>3#xfkRD<oN>bd;PGl?Q@jHh%6yA<xUicVY6)<>Np"
    "fsV=$L$`RC<7!3uLaav{y+^tO6Dm`QCy=C|4r@rLtdQ<0n>+DRjUi!Mr9x`y)B&1;g=tXk3_ZD=!?t>oqNOA`Erw_HCM#pP`N_D4i~W}hrFQg&LT!AY)t?H*"
    "95PbFu02Am>EZ1F44YAiP9>{PqB#QPp>;nn{A$bDQk9{X90;=1evxsYG-?_Iwu~%KW!ZkH-BP-+x%HY-xyJCsB|zg=y7&F2&y-9|+>_#n$AY)I5xP}LZGkF|"
    "Q;*KFLB7lkO-T$_PleaTtemCDP;+qW?-WB210ijUdqOJ;6&m2TA3O}mp{uBxr;uZrh}h~2E8uaLD3iSjNUM~Y;N`LX1WR$gSEQ9->k$?SN4o65JY`Sjq~r;~"
    "E}I0`W4po^pVo)q0rSM7c8)A~Dbr%aD{7>z0g$5qqtAjsYFy|3fV#l!B$1%l)&k|G!+rLlB<=ppA82I@w2~#7ygMuinFsAI+rtZ_QF%wI9QNYXI=yihr=}q>"
    "p9rPU@e;0#3=(a}oqQNLJWYpoiMlY9ECrZl%=F7Q^-Ne}ZBnW_<|oby-!!u{!=c<1`@#p5TIwkCYzH1>S`|jox%~~rU#KM#n~7ul=lhL`kT3(T_8-JJfo;10"
    "9@n;vIfH?T5r_N&;wVZjhWTRh*;v+OuHGbZH&3DmlW@4BD~{OH4n`lV)iBcVTjyj;^xtP@c$ZSNAWh;hhyoS7{0g~Ki4Ko?2NeY9v%F$0&iCR|0(|8fqt;5w"
    "T$#^WwBP)kdN=H#67L)-dJfp7n8wcNw(LBDHEhrkpxuV<H+#2nAPiu>obZ+ce(BC@vMunzb{$|14{VyE9Ms^U;4858K2b|TM9roh?X_DQH%8mxnk{fQPAW!f"
    "dq6JENEFt76EPwzYJ}xe!N+hCoh>y!<afk8rfBNO0=1eiWGp33ON?y!qDl;*@7M8o!!!HvB*R17@a6vjNBAKS"
)
_V11_RADIANT_SCHEDULE = json.loads(
    zlib.decompress(base64.b85decode(_V11_RADIANT_SCHEDULE_B85)).decode()
)

# Higher-alpha radiant branch from episode 89475210.  It shares the first 109
# actions with the robust branch but performed substantially better against
# the current radiant/Pandey/venks leader set.
_V11_RADIANT_ALPHA_SCHEDULE_B85 = (
    "c-rk<O>Z38k^C<_^T6&VHPYTVQri;D5e15J!yX8O0qn&BhJBdb+hYIwYQ$!BRb^ykWWHBqljg0_61(1aWyXt${P}-R{`1%0{`vRcPX6QPlTVkQKc9R(J^8O+"
    "|Mj>3{`SSUkN^Djw}1Tof4+VG`Q-hFo9(xM9ew!m%U^!E{P^Lg%d3;qlegEqlhf7x*PplBci+DJX?u13@#OT??Cah8?d9$7Uw{3-({TfS{PN-I-7nvoar@=_"
    "BZijze6rhqzWx5tkJmT1?@zu?+xGi!f4aGT_vP*F_~&zt-T&Feyj7n*y#3RcPouvYHEZ9R)A6UfrV0&Qd+nMx;Og@2cK@%Fr_aYLYQ^X6)z#tgL;r<_eSW{)"
    "enL&VADhEpj@tM6`pdpGwxzRgY7N~Srg+w{Km0zYlg3P^aXlTa?d5)XwG5j-I>Ydd8}#<lOxk`2-hZgh-mDq-zYo{#x5f4GcG#+@Ijj|HeK0^PrVIPq;9uTu"
    "Z_;fL*75W>ayQuBG~r1a4xq!L?m9en!Hyn8<_MmL<)yOkF4{KZE}@CqH@7w%rXl;`hD&ysis1vA3GF%eLwon{lLzi+1P#ACA-wnVKJG^m&iP@8N1xO;%O)O9"
    "JBYIntSg(uFwQr*GMclWEA`k8?l7TnZ0|m$dTmG59vAe@0=sga7~I1SFk?78m=5N&hv&j59+t^4cJl^0qp9^4yeGif%Qr>PE52H1U9sQTgIQmv(g=g)X?mXP"
    "FbUJ7MxUDaKYV@hh#kBb_yc&PIqbW)*H>5Dx3|CiVS97?;p)R*CyOMNK5Sas1YTHvx}d(vi=z?@kJg%E@55&fts9Ok5KH7bjvqNYi`CFO6HdRox&Bmm#4ypL"
    "7TbUUY_h`{eE;L<d}a?WNAI)fiv(s(PnJ6EzJXFRdw<CCPR`yueR_!=ZF?}<r-km3Ah6iG%2c)WVZViOnq)fx{;@tsb9@Z;;P6E0+2JD&Vcb$rpq;49k<y97"
    "@7jMm&OWrSv&tie(djZw_D7n2Uyds0;pwUKzUv-l%HgaC6fGEp>d4VC#HAv-@~pyBigopfPr-aBSXc1qRfPNaXh<;}Ca45mX-xr!510jTL83p(hr5Hccce>@"
    "fZTMk826AL*%9QhcZVQ%csL3WXK$xekb7u3=pVQODy%~E2)p$3C)g-=_}fE*X@8eIz<=RZV_y){d28iJgGLrw_lX&Y$*KnLaN2~)nf>GfS;J#I;h2Ke)guP0"
    "FHz}BR0^WfFtlj{O<7Qy4~U(p6ujQhClq8U2&x2QE*GORn5|dH?SrxT>+)QPN^j|&L4-;n%tQxShzeFn?+}&U6eM~<VpJBe(HM2nSX3XqVl3MC0WY!WODyUJ"
    "o*+hjiA7&x(TEwicre;65>E6}A+R+<r0*|p{v3S<yqpTMh)%AUTRy$F*kES+CO#Cr&JEN#je!*gJU-0|LB+$<4_^(9bI0QI?ak%x$L-C{Un~(=XPv^(Xy4S)"
    "6P!33{71LFZnWc*)zBWWadB>uGREKdmqrU=``Kg4g)4){+s^OJ`;_P$p}~^J+Hb%}<i^x4cb+w6?w)L9PEmG{Q`z)7LBnu=&wglqLR%-;1$>`QkT~BG#X#^{"
    "C5q(|8277g8I07mPJr!Zb-eU~Na*!o!LuZ(a$8?hgDn?TZx)KG?Hj#6M>i2=TM=Dhtg4G{*xpVvnbr@su8@}<j>@?t6G4QUHnXt-2W4Ntrc4~IT5{rI(?#4m"
    "$9rh&B2PSgSzzxD9u_SVV|MD|oZWsJ(6{A|fgl=0=e;^+W9YHcXriM`5@b`OIpl=H%%upLt@jT!w&`&b!ERbuD@t7k83VbH13i9F<_T>{2+;N-%s%3S7NP)K"
    "kb8N0#j8gS)?c+^#ZVtD;h_-4Uk1=_LQ^xDPc`%n0&(zmZUvYDrkDuD<EJwL`#9JEUE@#h^D+V5-<c*+(P<{S0w`OUMl@WikduMa6?7z#1qnVz9;xiL*<>g+"
    "x-<yW+_1M~Kxt=*_+3Y40j1WXgOo;-39u<0X$Ilpv;F$|ioNABy9i`IF05xqBEX)&lL@N=Boom8quuO-5@KczOTjYCY$~ZH)4RUPO}K?QD6v7XU{RKTQgYbP"
    "dvJ=fhkLPWs>9MV3A>}N?*LD>q@3iFHG;_MYflEs#y;RxOYFK>Air<Z)#b-`J)(MsItuaqMQV&3W#af&`#fu4SGraZVS9b1E}B_6D6}ydm*3j<oFOK}Brg=2"
    "QwmB9x1&^<w@g+M^}qP<lJ8c=t^?!+klgG3x8CUq;RCV7Q%hJBp1~>QNX#fO^>?G@_hu1L;j5~i)Q<A-wq}oyNk2*=KoD8sdL%h2JxpL23=i^^{BUI&g*Nk6"
    "U~u;sB#C20GmK%GS);MkqEZ4u4NH)?9W5?!Lc357qJY_wXsF`KnQX>ZvEwTz5|p{bpnh%A$`-g<Q(cliz1iy2L?UF#HBj^gJf?>Bo$SZWD(mTGk3=&{*47;o"
    "P{?{!Ey%khqqWR(c%fD9q2y$9-@%_gT>XhHou26@<RjyI9;Iglv>o$|TsWYZ%$n?w#~lJ0%r#o<FOfm_SGZ9C%OAdCB)b{3Ko;F<-RG=ClOs~k3J?VPk8LY)"
    "RiyRVWWp{aCP%mDqw4c2(OXGmKe^F$v5OfwiY+>jG6ipKWs>wTcgDx_bQp)_$&x9!WDjoKT*sql2%av-^$!^LBqrAaOeEcC1~`BP4H`v#plm#t(@CuoFhua~"
    "W86`*6XpwKEhS39SWARfySBsE_kqG-PbqI>22HiY3|;^l)P#|{!&h_SM~AkCQC-wvet4MVHEKCs(RK%t0P{4WR$v%pwz}O5Ql-5jZcB%dUf<58omGwxd`PrF"
    "HPo;od80TDJVlv%nVC}$AFM4w+E~W+u;0uMrQB?SSR>lI1%@oUe?t$UfCux#6L2r#0s~?do#?NtA3C84c1^Y2^>su6oNyS{6{;rv`yYAp0I0@@eMCtD@Jj=D"
    "fnPHae%p2Xn{F@;r#gGo-LzrFGI#gEwDI;tojl+nmrnk+RJ#F>mu1L0+2ihi)|GNL`5W&<9Av-y@J9!csuC_VY$K1>tRf5w%!~8N3H!jRmK0?4hnYbfa7qc-"
    "%_nMTsTiPFI3-{?2OcS)ghdpGk_e^ca@-CzYC3}@K(;v@bj@R=Y2bN`Z$q+a0~3g3{koVfb4KK#n!2<oX2SVCZ>jw_8cQNmiH2U_=EpqoL=Z}IRsM#xT|wI&"
    "){d!dfb-JHBYIr&wr6Ntj0ZspVYZ>e0Yae8;EuhW0Yj)<=x`|%N{H4&qPjCUzbTi89v$Q*TLd=HilTT1OPbB-cRGf(@#17dCPN67MeNm}=o$iOsAP!dR`d?w"
    "G~(^sX|&2f#ya7Xt}`{-K#cX11Tj`;$Btr*zhtRzY0}R6^G`xDO<H!WQ&k$%|IESz@k-P&$S5L3j9XC{%VL0F#_%B`n(R2~W^t5bE6@`pL55D?$WOsaSy6WE"
    "BQb|QCE%7P1MHEgLQE>C%p*feE5vII5+WLB6fO#hQ$Jfs-R~6dJ-aui$!U}79JCkMoYKrD8qbolh-C~^nvbnj(VrxWBx@vk-oVJFAwb}mUaBI-36VUW6roRy"
    "zf!zDWoa&_763+KvgrNZ1Nv3U+t}<?R>#`jrt+a?B=e!QBzy3$wPL(#aKzSK%nm!3)@>oz%`_dC5$3h%8cMo?Pe+?ZPA*}LBt1yj+3bF&#g3W%<N4OSJc&;O"
    "#R@Z3dS^r6LsE9yptu~I4NN@F&nMPus-@ZK#J|ngBoV`&56l2mlBa+}FsDum&XRM%`eHguYv<}FxwMo&j4b`zwKn%Z^m@D-4_b*C2C;DlaVbeo8_=_Pnn2I`"
    "DFHp;hYp*h5%XC;5av@PtMKSj`m~5+bTCiIt!btmPrJ|cxht=7M?#e7(w9#N_95*!5QBdp_MqBpFU53O7o|EfO2j=TGirwR+2Pl+fsTPlk>*oe8FzYj4q}ku"
    "E27R}ERskqSMbhYz#F$7q^=f>l+2VDLQHP#WWYTyxk#s+BZrd_j;rR#5TRWZ@HB@GML2b0J2P>yhc!_MWps6T+g9MFh~dtPk4klf42p${UG>5pZH8twMI5pt"
    "z;onvsWOI`MvMC8hwsCXZAp=KD4S~+AcB;T<9rE8qkvV^_Ao=b5>lTm-!apRbw*-?%Be=fEK(r5&xTgofms@<E#K;p*8&Ykx<7qE3A(N##flZ@q6?b3IZ+R2"
    "&l;tN)}CgeZyd<ybsu17{?bwM#`C3d9sLfQ<=T%9@+8|^#C;wa+R>YA*IbGeB7z4?B0C_*tUyzO@n@40y=Y=W5S!r}9LBec%0gsEE!02>Jv864W(;}zm6*S7"
    "`vC|i5n2N-L9KMGp$?(W@SvO_nHCn|4<M;e7{|<dv;T>VGXglcL82TMR>06eWk<snQvlGR_i!Uw1-hshA~V>=u5AKEG?f<z7mI8V+^gHbX~!Kr(zL@76y!#>"
    "bxb{=FLYZ~Tx1R;?Q&UxWhb?mF5m;eN@*P?UqKIStJ$n-jVMb6H9n|fEfHyQrj(FgXp+DL5;EW3WQh06mOGJ#NI=7Iv$ir4!-N^nNK#UIm@9hC1Sag<QhQx*"
    "wlh;G-Of%P^l3KRn@u7;y=o;6Eu2gtEr41x?c&|Ah2`mzt8blIeUw#GvhS{y;yf>}JrN|**jus8o0r?H)Z~lg%+m69kFHF$^qvMd9C@0yl%O?d&j5@%%hr8="
    "USQPOQGih;OPmLWqF8bgwjTfw42dFD0vpUX2>O&DJ0)%$Jzhv334I%CN#GoaP8GoVO~QAbVH|oYse?NmW+Vbem=O~%gsOT=fw5|E)dn`6c4u0~028s<4FJ?E"
    "p^5gZmVyW&%_!|g6V`?j&oQ;Af-q4k^;D>ED}va?h^bVU7n*5JgoBFcRx9e;FfEj?$1kM8cdnH%brq>ii?G7Pt8HDhEMUXT6s4haj0pk;dpNOx3XErUqPE$u"
    "c3<uyFTG93Hk^fo{xxP*wM?F(&{0_*s@)9ze{sdAb23c{R8E}29xgRot(-v5IZIG^)R{r5vAro_z+lqnFLUDa*`jQ$1~OfB%1)bzTq3s&%A5CdB-kgl&);ba"
    ">rwaCk7&c;w6gN*nXyQ0(xysXlZ%L$=CsxkK0TFeOjbM6l6H9$p`+%K1-M(7o>#!ULYb&XA(nBhL=_M{41$Nj$XG)`O$>p2=rNdOd~%TUjHp%%VJINjYm*KF"
    "Mc0sn3?Ihx1C0t~zF<UzBsW0Z;!lgAB$664L!!D$uok=6S{8Lp@~R7=b=M}Wv(vL(Mgnn`vpei>&u{1zEm4JhXP+!|hMm?3tZuR`5MphMz%m{H5Pwk=Q@vE6"
    "aBbX)7<6UmpU5t80qJ~YIh(;U*jvf1Pp1++=$fyS_&8c%jvq?+3eH>X=oX4?QLaolmYQp^z<d;?d!Tt%E{XEj!v@<YvYKtYn7Bjzq({61eXvEKMwa*YwKce0"
    "@^GpgE^+pMN!-}xf7MXoi6R4(A;^@s^pYc%WCKXct4gOaK}*`(fIpXbtBi`j0ZT?+Y|wZy33dt+&n&cpb5_#*Fr)r4_d0r<P>gF%Bkb{pp@hWnjges?TQ*%+"
    "KXA(y<MTR}9Zt(xTac+p7Fz-C+KX`UsDz6nko4a}xEOS}z#0=xksk<YDpVxbyt5@!@&#cgT0hIC{2`(QymDk$Dw=EU3W8VBtw~&zeOP0hbOWZN#Pi!qm9rDH"
    "L+Teq9aw_wiw=He$a6Bf9R(suIP6Ml=(*6##RP1~68SI{t1EjLL>@Aok*3n3!*{~)oS54mDgv5e*8KQGYpWLPeH#_WH7@W7>X&>i%a_6@X|_wk&AnEnis6=w"
    "gRJt8B6VKEwOxB-(!r(+1+4#o+1BF<Vw@cU0h~xg;r56OxzcWfQeIP>>Vq!ER1QjDF;$cBu~G~6^kLS}39=Lq9@=ccsDzyv<Fl`Fl)Wkf4pg43h8hEl{C8+s"
    "{!d0l8%^m`Pe=#2gd31&vN=`&x_R^BBJ~2s94i>Z%aU<BDZPGo_N{s(Xbgj8RBggTqA}Lz#a^OE0EXn%R|+j_Wd|c#kFO0&F<)|M%vQTLCJY&{j^<w#(HFKZ"
    "5=nmObrpgbbw_ZL&xV8{4IvPVStcqLg<Y_-0hTUJq7a|fTulNDp$7y5AuoC?QfH~Ay_)h;PLxe6l-y2&^A%N~<EBm<LxChmR+zNi*4QeF?U|=>Occ;#yd_C`"
    "%}RIf;@XP2vCB}wXa!94ukI>oB7Jb(B8TH>{lC(fY6?_Jqv36lfQDlENzIi=HQ?5i1T}G?<m{POLWS!uC<qcjel24-!y|gYW7H0ux^jv48C164pXFj95#yNM"
    "gVM6N45}kEQY)?XbPcw_ne(howI>xs>0cS^djDT+2_-@N!B)ej3!um1A8_UeHqoAIZzUmD4a6hKNuk`kGDG2Qw;l*W%}<jF5@b`@FZ-BpLrxG3@ktrG1pHv2"
    "$sYMGrP<gFUKDPz^;JoHt@MYNztVTac)n0_@5)vx-GJ82-r}J~vk=LW!D&`gO`a0fMm+M`r!uT9y@&@HV9onSbDM(<Z6?c6^V_0FPN#c#e8cYL*EF+?mvGZG"
    "trNU9v9_4#lGWRxX_e>+EZt5lvb^b_RnVN{IYar+Pan^A0Av!rB;y|QUDwwQO;hpZr9%+_%6Zf3bZrF2NZy2r<9oc?eS9Qt^vTicmnjX>1#BsMpTx{C3m+97"
    "%6p%sdeePo(k@I%3#v|2!^%Fi*qTv~zNKcSh@wq=CH7VmuN(yJwS%}_fH%#mi`R80UvUzRt)2lrX;pK7T7;g|1jm_^Oo8K8kI7E*!L@*{L>bMGrx&Z#kw0cz"
    "BJlFJZpzKRL=1xL;7tSw?%_N|s}9Xf&Yq~*bBG6?)S8GOZ=HO47^aBkBfttBBq_m)+Gb7E*BR>}dOIzrc#xq3Z^`OF9kCihLJ$J{;0-pOo{;Gk(pF^S`XJs^"
    "AO%{vr)bQgz|4WK4O|p{h+I@Ufg?d0zEH>$T~Q?J^w1JIg`yM0bB|lQlYy~S0TTx!ToQQyE6&}**;64BDFIjUt?BW%i<>TMpaQrYl6W>tYr{w~<E*n<Vv+x4"
    "%tfZ;Z|`u|tZ2l6jN1q=m?-;?oV^n|fJWO17a}Wlp`xFhRupGJxrNBJSgKtWDQP#?JT6OOnn(iA1;d{EM|Dznft2Am1YVy1=4rxb_ZUe`6@6F1UgmgMOufu@"
    "^t5S7`cl$XJA!%$#iwAl)1xoUPse7yBF6;VI0rj6^S&<;me^ZYr>QMmuZ`8K2a$C^j7#9vMHv`qW}x8#)8M5N1we7rp@f-z8Bt0Ji-}>+`Ut%ey8#=m%7L=D"
    "{rgyDvz@>SpHBsm+|4neono3K&T6n75mh0TSA9m?$bcq1g1S3?aE)87I;c5`Qi%dSGZp5rl;mv*KIzuoksbJH`L8&M!Y*er9Gx#7)nyqlb(08rwGb^DZAdu1"
    "hAiGBO(YjW@evdaXsDtrlkT$#)`o-CU!y<K);N)DCAAKWEAw!sx+oL<>>=*J0E(?k3+*WH4<c-vBIE|?c+-pYa*>5yUfaf8xS+wC2U3+y+w+6lo{OiiGxG=g"
    "_0h`Ae5buyO}&ffqB~<pN*k(mUR=&_&sBmT?$4?l_NKbQWF*ubxuG6<MQdhT;NBBPNHB@?n{XM$*CUXL<jT0D7F<v62UrCL(MVDnWl=ycM+0Vu1QcVU?u6ZE"
    "_ks4HL6dGPBpNx2N2#voi!N#jM<int(u9RYgd5-MiWiRqkY40)BP59=j|jcd0@{sO6FIWssq_2>1`VO9*cIc}ktXCUXTiA4oFL24w4u~eYA4vQQQgFR8hcw("
    "q3sKR>_EdLNO3yJwfGdUcfVFj5R~lGdXimS33&>dKil90z|XEF032aM*fR4iFJ~F=b@;|-HNfbFlIDy|V3zR=ziOIc#Az|K9x&5*TjJX>fYI>^T9avg-86|z"
    "+I+CwcFLh?1$Ah}I@UeCI2f`CXHQKxc>aI~q#3Psno*-!(s7$eGx@;3Bh5&_!k#9{$Va7^p{D;=k4QCY24gkAQ!7@pAPtF=_7$_*aHPnQ)LKv8QU1hfaDvAa"
    "9cq1USV4XO)&`+A=v1-7N?R9Qp#Ty|xdQYCe)#Hp8rxZ<6$ojVU@ozi0Ibkirp4H62;rrZu#-y4FM%Y%r4z#Dnc-*m!Fe}3#R8>Tj9e}+)}w4Bb)NT;rO-7g"
    ";EiNNGvw$w)N1osRLI1TD7G4T;F)7n<gMV&1XvQ+*(Ic`B#fJR%E{LlO8K#@ZZXhMi5wRU0tcMg%Cew_$X+lbc7oksW;jhDW`uS#t=PsnZM6QG039_7uqcus"
    "j&q{0mQ)dg@|)5gPA!d#iqm<pleGI?219@7#^)+s=w;q73gz5q@a{{Mu%}cd?BQ*A9<@kVg@vSGIwBYQ!CiVFZz=DleT;S8$t7{Zr^g~c8H;8W<gwShkl7K="
    "OrjD{Ynr=iH0YuG0EhUrUR|BiB+-E^!eF5v@Kz7W7p-OBS0!^E9XFE-A%*>Iz<HUi#Wdmq1SqH=#8KL4US(sY&fA31S(TdaYGtKvw&q}Q1Y{ydAXV|H?v#9T"
    ";Fj?~vV4J2FLF7)Ufq(4|00^1&p#@ybFJ{!F#ML~MU7rV-z8_X&3$&sWtY|V<R&J;Dr>1NFBud?=?g=Um|>JIZ47Pq#i%)Cd2nBzUd74dB7jOnN?jInjTAsr"
    "GFH}no>f!hgh>igQ5&8>dhL0^GZ`Vd{i<PASr#=TiTO*lD-Lvr?X0}QW)r_=mwV?*+cpoRR(r4-XsM+5Ni%y;)xf-Iko}XVPz5birco2(V>S)~m*Ly|J$`&4"
    "_Ruau(IvRe)me4wg7HYkMW|MTTH~Lq#r4{&#M73^=EV@yDtcbC%li~LBB)r!Bmo_Kt~ZGyK_DDX96vaKT7p59!8}MN0Z0o{jk?edsai)b_V}T649%mnVVFs<"
    "ihQhtBqi({GrQ^Bd|J0F-qsX<4&`4<w4Mo0c^RJFwm@jGjT7tFaTXc2{IMv#!nk1hK;U`iB#HTBGvHoS7XrmW#kxO1sd^@_s@@y4lw3-#<uDJY5;nXRC})V)"
    "S_l7)ndMl<gsY6<_14c5f+(ggqAP?_SU6fTQ!S;=8?o%W;tXV?0li_7Z<)kGC5;1nMsHji(7B`3tk28}n=HDCkaX3H*z-c;d7<$<K^o6XHLX_M;OSJ;0?1BJ"
    "(oT({6JO7yu%oWJCT5GP71RR67G}lVTUWr~y$CFX!asRo)#X81p_VRLQU#i`YwhKWY0<S5DjGC&rn0n}ifpMjtoSb)cggx|pAuZ$c8-O|HMw7nMabk#?BXJT"
    "2a2_K+=GStgERNM27*9+pefgk8P^9YH*aRTvx;{4s`B1pgWr3Tx^8><T?kz`Vj@bcq_)Y}aw$M_34qaDaZZ$UrM;c`_0#<XRC0d)49^}+EXVB@|LVcxQEGGP"
    "h_^h36o2Dwihy_uF6tx5ERZxNA(}z@m-6VPft|^Av#cCXo%O?u+0IK%uYlU~+)H{<Ta9C=;w9d*7tASo5kb0C_+sW9_XlUXAXc@yZ~vlR1XRmc*zRA%D?Tr?"
    "Rz_uNw_8A)RCd6?ScCv{7<jpmR}`IPrXs))y6AV9Cjet5h&PCA3LBth;x>MNhU~POQ5+0#v;^UTm+m=<FZv-poA)MCOm!@K&t#}OT726P;zf=LP4KVo%Pr8i"
    "8QE!=5*6!f0Ar}uBuc7OUoVpXmG~E$CyVZPvQrqDEy5z+P+pCJ+HTL%#hji*WCC#rAV4<tD)M(LB0tRny$6c?*w}?e$>ZF2{k6Uv0&G55qOkt_yo1ea!bSKP"
    "*#~(1kad&=zB%rz;X1U1W{WL_v1}|!Yju&3KK=0Aq)!iBmh16_PtT4a)4L3pjrvrizCYHIDe=U-Y49nZl|=Q&Sg6|ras)QTyL~kU9j{_?pDe!>TzqRf`(A<@"
    "T9}IxnTa_}W`TBh;vtL@o7jc47zL$az)k1NX}iQV&e6!I@g99t;K)AcU4#aSw8L1o7J<u^Qc~zOX9IcqPUY1tW~G{<DkAN!P8v5Ug7^ZEGAJgcS2|IuIEz#-"
    "0&_H2bQ83i!4MAUMzA~2Cj`2t1hu$Gc{+`nVX-@A=TNwY+ti^iU@1kbgmIX`?@lVDqac@xCh@vsI7O~R=jWLcOIkH>N{&(tcX_p6ft0hI!!Q~lE?P4PSZt#k"
    "*-F1oO*C!p*jQK%&qL6ED$@rsC)yOvP)=goGz>M6O9k&x)^2t)RT$@@=IXVzOkSPo3P4ot?ToBv$zXX3NcE!j$dwk)o(0?Ij1=8FGPVzgU-b0x?C3~7v>vBO"
    "+c-jIkHQ%_9s&=*3}ju5NY`47#3O-!fop2VGTr1}T~{SxY)KmNZj>FSQt?h`Cyg!-uT0T#UvQ~n=~1onB50H%=%f^Zl*SCPoC)`2A({?Fv{jv(PRwC^1$HKY"
    "b#dQ=prBSyrPeN09*a&cA@KA8W=Rr^G*6+?tIeJi%`TCRc?XonwTn=;o>p<9e`uI9u|m$BT(iTI9+-;+*5CvI$qi`0jbH;x4Pvy)OwDR4yOdSe9oiwK$WxX8"
    "l5Uti5oohQwi1<gMP!~_t8@w#D~CwW5?iU={*&uan0H`qV$4iTgn{YI9u&E7@QKx?zf`G0S$SA`jdpW-)Et_|TtDb#rx<HYt?5u6yI3_jNvm(F`{p#=#<d^?"
    "(mno?!A`owb#<gwzrtnAQpAha@akXTj4W1!hLyB-%IpMj->yUCNti5wNkQsmK+}%~9F9c-f?_5fV_wUkM;&Bh5n>lY6miAz99frP<r3yANLVNGxYf>tLba?N"
    "EzYhK5n^VZk)Z|ppO)e<`=)o<aJnN^-f4-Io7o)96u=YN5Ft*AC`9~*wVQlSOkj*Lb$|F;652xV{#~}}Nb!IGfG~4?&Dixa*BjP4V*{&RyDI&eIgm!47h<V7"
    "X|Ve?o6;nSy%oQ9Shmd+gePsL9P@IM?WsW)M+`b(Ntad;s%@FiI}$$5;uUW^Yyv2MHfI3`116h+YD&Ku%RX3>Yic1Ve-r5ajw4t+9+b8lUnEPy_tc$mkQ`*k"
    "B2kN^ttIsCK{DgECqv-+*K&Krh5bI(&BU#DXBB-u<VG@EZ}E-z{aOH4Sev6JcR!382^oOYj=?+B8ERvmk5?sa0BmVX8&FU}0DOS*4--pRg7jjh+9+_9WM8^V"
    "G%8#L={AKACr1Tw&0qS_v#HNMTDaTOTW8w>V#ZSI#_Qywsg0y*3r(IfDr7p9;jzryX*3$PQE8g~AvHWNkM8~Gum2DAa-X0"
)
_V11_RADIANT_ALPHA_SCHEDULE = json.loads(
    zlib.decompress(base64.b85decode(_V11_RADIANT_ALPHA_SCHEDULE_B85)).decode()
)

# Current leader syouya tobita's stable executor from episode 89511601.  A
# second chronological source (89512693) matches it for 717/719 actions; its
# only material difference is the late shared-market sale order at step 624.
_V12_SYOUYA_SCHEDULE_B85 = (
    "c-rk<O>Z1oa{Mnm^PujgDAG5M)N2XLkpzlzV?7WC19%Ms#`-Y!&G3J>Mr>ABRYpce=6gjpIlMLa(e=J7GhRgGFaLY;@4x;2kH7zZ@=w2<e7^ef"
    "<>cGx$$$LzU;p;s-+%D^<3E1;{XhTyKi@z9a`OJe&G!3mM<0Ir`nO-NK7RQ5>iXpL<n5>3$?59;$6vPFci(^b^Y;4F$CK0Z*^hVcw^z4+{P^4d"
    "osJvu)7KBz?|%K>jN7k29x=4!my_N0%k7Vce*AQE`~KwHv~7QU_vf2W@4mjh9e;hUvHO2}J#W?L4{!ha_4DYzM$Ou{=5+k&uBk!;*Iv8k4Y<B~"
    "yWRhG^7Q$5MXmU<y}mv?e(1l@urKeo+s~+J_hWPT&r$oneEPa?jcw`dC$)xd4pTg9*kAsb(@A5d)3~0F*7j<@yjq6MADv<N#tnLVWhQOE1Mfdn"
    "XK&Vw`|pSA_WR=ccsp!W)Ew4|wLTc271M?Neekbtw>RlF2<v!y9Jw3pZkq5U4F}L+QFk34yI@BTB69@K!}3zucNcA&ahK3U?VDR04%3kRaKj}#"
    "OvUg4&4l)x`=P!2{p5lB89~GEP6+S)ypQ`)gmZov;?XDd&9aGy(+=Y71MA8rF^uy~u8ijF>q<SggF8$p9NW83sb1SrwZ{d0v%s#LB?kAf1I!o>"
    "52k}T?ctd)iic$~jNQC}&S+}A1@8%P_VP^;^op<6Sy${&?7^(BQ)z_3@-#iqb(n-{Qln2z{2#u)c*G7~4EzB+(j4~P+fUcm+qbvB{$+b}`{DY-"
    "zfKlODt*|rwh6qj{B%KmlNU!N7#^)P#omX{99lOVSs<3kbsRr(b{4ClcP5;Eck}6U;Ss|`k6LU42C&HvXYl=(qw|?PxE#IDqAwDdH9cACwEG51"
    "&FuXl%R4!H^YrN@dbI7qXrC6kM}oj&?<!N()`$HT#%Yr61o&lrj^_9n?7`uQ(zC-y9KyJzo<KWMnIokWhwrt&JI+3|ud~V{hSBLVO!iBfzF&?i"
    "=i%w8^S<jIX3F8L2ox<CgzCuAF~p@Jy7H{TQ;K!<h)=<MC|FnU=v9RK_-IHm944p)U1?1Lh7Xtpa6zI!%7?pyw0ERSkbvBDu^9J|AK4M)uy=<b"
    "cX&7o5NB_vRFHdUIp`m_0xGOR^a#83^e5OTclh5!f@!~(Jive9R%2ff(|K#<NP|WeTK9<=hsml2?{M0L$(eoS0$IajJmHvv)zu>gt1nUMOH>M?"
    "(lE4X15H^_nh%Jbs1&^3&?gjRDF~_rV=fn?GMKGb$nAr%`Rnprh)Qqio<W34A<RSvS%?Z&NbeAp-4rBxL1I)Eu+bQG(O6U;y<#ld_W>`l=u0f>"
    "2A&{BeThY1V$p~hxOgzyEfP-jQz5W5LZt7nZvG|u40t&eWD%WQF}HkrZ?VD5_Dy^!c%2)la~cCH40wE+6@rR~ryqVaG|nB1FSj>WyPvi<H-EE4"
    "V4ZaeL!*6DM^A9#Z19I}d);WqC##`7VB_N4B4v!f@i&bY!uE^DlnYk|kGGxgoA)WvIYNUakF`GmBas_ZyWDx!l(~DdkvT=#K~81U>jVwM{XYAl"
    "^$BgAU>ERxIzi%mOB4gaYn3RLOJLj|b<1F+u5|)zH>=~N7eqp@2MeAhNtN6Bni_1msCu(dRBhkr{W-dcDBFtY3S(7Wbi?*`n#r_&uyuvJ>~K`h"
    "C7B2!)U=t64LB(K0ybshXw{Mv7n?5P);ZooTNioa;mZPhckr-inHaNE7w7Eu(}2D$cMJs4AUf~WF&jgVl|~aCWs)G98qFam9A+*>&}_Ybps`Jl"
    "n+SH(!dg-4GRPRng&gSdgECKOOG1FQ7h(1hAG8n!*n-^4(<{y&Iaoh$#fqUmTEasiioXn?-GruQGM{Sb8wBFu?c545157ayipNi90`_sR1G>ha"
    "-sfcky1z3`qN3AGbOlhhFpX%qR3Rq=rz_}4A`23Hj671=YqQBvYIJE3rnzBn$$-+%67jo^%mPZSM+Yg5CKF&&I?@cn!)N=aPuJ`%m)S)i`*C4C"
    "I}!o*1fEP-6(E^_{vYjTACwR?Ygh`FVP;cFHJRS^Rc^v9%t46_f(47R{F9QyhTelyls(*wT~i&Fo=Mmpb$thTvL)ptpR5r?R^NIuP&W1f=Pj}8"
    "VuAd=P1jc+-}Q*<8R{s+_pei9<R}xzx7ue}1H00-f(YB|GxfTem4iYXlX3a2ZO<8ELQL{Pp*f|X#Be)Gm3hl#6;c0-zn6TsGIkvxFM#A;_s@E#"
    "Cxj2g7Edi<QFsQYlp`^tz|`N3n%|p6K!qPw^`v%`hqpC*d`$XL5&?q93fCjaQR!g<!(e!jujGd-(<ro=w*rH^#~?`@Bbs3h%gh>$r52SE2x?e@"
    "#O-KtffL$=au5Z~mPA7pSI%TJwu&8JIgy~uB?k3tlUBCC)tc&(^y$r3rzR31ORj;UFW@mXwC`m1z69FTGNyET*(1@6lC^b*1QfDfRSWVi$!IOJ"
    "9A0RZdnh^C+;{Nj57&QXfJD#q6Y`PqJ&)2e0@{vwMlKvsOlD1X$m0%y4CWdw_Ls<@`zzcifaMQAVkEm6v_KZ!YTf6oM3W;@&k7I(`op%BxGK{6"
    "Y%*aN5|g9b^HKGAmFTS`vY*`Oy4b~x9K{wLNST7SwlYb2m^<U+c{+^4@?^;rT(So@Zm#3eGXzhU<N61TdlHjt0Va}eGy@#Kf(DJEK2SCu%;}_7"
    "2^b=H_c89M*$MLnvX&C1V5}uVt6kgS>-#`qu&0!_F@vVsVFoV%4Qj&3-Qh=b;zx(JhEZMAV19U*<TYwJUD0+2k^u8GqE=uSWVX893sR-MB5q5E"
    "kY3-;rJYrd4}3_pKsD5`B6*`Y4Ln7edzqP24<D>8LE2cx_OL&h9ZI>`1hGc6cMA+zcK?PRLIDrvhbQ1(!UYBdCORP>t2dp{1iPl%?)o~S08Tgz"
    ">k3tq{{5F+J^-pQVjoeG0Q{jrx4^d<2*2&R{jwX3!>P_5bvJETvCQ3lFm1d&Q6~?0$d!}7E!A$o<7FALPWHI_%eqp|CV%6dh=c5RAO6`vq^g7q"
    "4co}0HLD1N0`ua$a>72aswD*({b6Ph2b@v@cJqlES}F$U6;26Q&Vfe?C}9!Bp(H|Sxg57cjhfD236O102VL_RX&QJQ<J*vI+Q0-NS-&o3%bXE8"
    "sHQG0ikWb}&su6fj>eM6RHC65xcM<pJQ0M_T$R6JZCB8ChqYsB8{n*T@`xUnyzLp<7UMxsLYQsnaDWh~Gq_`KXTT6D7dl)Dg%YCmkf`nq&Tq=)"
    "p+^UK$rgbPw4x}U!IEY(`kjtpZM-<ykjW52Wf6NdD7uCK8Y&s0xfQ(wIE{Gwb{efRkg-nqr0YzLHV|X|BteYTt7Ato#y@1KZ)wtA_2-|2WSX?>"
    "Sf{EqrvI6R2jZ2eV~|lqiWs+|FqXvt!HnTUL^RoP(#_&1$5x;xNP-NVz>%MVm9nDj*hgXxeM-PBPX^c{QH7XPP?<-Dlvaq>7$ihA&L~_I5~qH)"
    "kh<R~-g|a$Oq0_l)j4P{usNlfO*Eb*Wf995s5Bp2tD=8N6iL=d^t^$QO+$ddF}+kpj1wYxJSjq-7=NXBeag~YPAve8#AMO?y$AGp%G=oNRaVE^"
    "-lp=QW+d~WwIqA+ueD;lYH-BXUCa(Um)30|*UdB?ml5W*=o+fYLMMbilSfW&VT>j{$k^HR{@}%q1>@rh*UUVLQ3K!XnL53*G4MetJ8@86uBlGb"
    "Ru2?_Kul4c`?vX)<YGi&0rO;IZlO#Omy;`nhfBr^23+AFLjY;1DQh$``Cm74Q0}W7UyQfsK|KLR>=GynmlEl;K|h<P3H_{}67&PU=*LD_cR+#G"
    "4}=00=_@?mls+xuAsx&U@^6}{$<uyxeQwXIY?2T+y7C1Tf}uz|GQ<EOh(@S}+e>j@)<yA-j2m&+$&9|CeRlXoZJ=x*;-vW$SH_**rh{l?_>px<"
    "VfRHAf}}j8R07YSIBrHreJ&VHS=M4uiZ;`ZfV*IF+0L9N9oj}X(3)vO0EkiVb9)N4krqHLCt~Xu9&G}~kN0i`g^GyptR^Ws>xi6=6~XF-M_Ob@"
    "<N<P`OH7D5&rpfj2Bb#%A>T4h(tr}Wb}=GI201k7=Dt}ThjIY2BZe||v{_<EX;ZtIwkEMi!r4p9i(<51E90O+k+gXPSQ4x0wY8iV!jP%Du0>jr"
    "PQ?mw@vsyCRW7!!xoh?i)`w5J0BFu-AIxSRQYb0m+0u}Weqqhh=tswIlI<-*I**Ln=uNh3PKXXE2Jq0J4M-n#)QNd}Hu)S?9ZLupGyFv1Udc6w"
    "m#E4>A0v5@M28JAW{A1!wi_UZk8l_}EiJU9@YPG$9F!jvZ3<CU!cyN#iNSrFGd2idFzp^8X)$EiG_bW{gEhp1sx%m{z}3_gtM(F-yB%A}og~pN"
    "dtJ!H8SeFL1P;4PnY8V&R)SQ>VP{#XK;k~Yt{3ODb6EmOZ`?3x2(_07@RX4TSXz#s-7HKPBRE)Ahl(O<8DY*GXw&9LNzHG0&&8aOjP-sMa~IMC"
    "U<8yHnIv3gD@-`?j2<QBin(&v4fCaTyxwwWs(^EHdG_q`JD{>`7U@}5t8S<vf10s1ny<TIi?pnsN<}g|C2J2MTBP3W7FS_sCb*jHq`K(16f8MC"
    "vACNT+4Q@UW(U!Q{Kl>bB6xnayvq$ooTe?ka9jEeFsL(5nSDMGlxk>vb`+pg$p@!^NjaX!jpUV3kqshg?KW925eTjX3FwqaS11ifq6XEK@rh*t"
    "29J$(?f`18Il4*Mt^*DLyE<pg2{1evWNj70It2Ux011e*?CPJs<O_Et>nxOm+A!}{0(7QyE&e@~-pQ7u1kIuREp{(Wfwt*8C}IC?yTmImZG{@B"
    "Y*HviQ!V(AsZu0*J7|a^vY_&F7RzDJ&kqx$p{}{cJ7lr3QD`c0qFm5RlC8k%o58Tuy;YwWVaZV?Blu+^9*|&;P90;+6%X#%+pyX95GTDn;B@UI"
    "5E?L6vnDY@LF!tU&N3LAsJPA2h#2REbD3(H;u@<cO?MfrDl)n0qz-uAu+o(&on9WCCbNH`+YHUJn|2NxMxB<;ie<|yec~_bC>Yto!6)KjME<h@"
    ";HjgQoC8ZBNvaDZ@8Vw5*uoQ=TtCDnMQ2SEvI#XLf$6P_=wl5S(G7#jRI*n@A-yP|l|W7^sGfOqJ*+8I!PyEf$!u+}h1p~ng)B%TxDk{t1>9|y"
    "kpimDR{$hqu#;78^-==*rB__7nfF<?@m^RFDACWrAP0t(2T9rktg@m;$u1^I1!j+p#muo$h@w-|Sk6ITdL<5BfLhXR%^*I&1F##M+m&PKQppA!"
    "pu^}B_%kX;QZ$s6A}|yu;GZmxrF(~Y%P3t24zi5(n=Fnp2ok>rR-R^7MggxF`R>NF6j9EtOEcE*{_M$TWsDR-8U7sAn~2HHQt}CK=l$ssZ#qVT"
    "0Tj%*=Crzs5`s<FOUv?L5hsx-*sL^+pMkpjyRre<*n^H}IyQe-=Olp4j#?T?rYR;!cd?Z_-$e`nA4o12gPt;b^00~(Djw^W9Yo30Nn0uzKlrN2"
    "lRF9<Ghm49H~!hQ<}@dE&A4PQ0>Yyb5CSK&e(bG6>F=fWgF$}_q^;w^dkR&+nKmZJ)>;tWp(U$8MouoT3-AuTJm0B8(@F~7_MLr5Ta<>yqI~RV"
    "%+^#m6D+r;FdO5^QIDbuY|}trie?_THmR7JNb{;J8l_0MUYkI?VgmyZN3M2xgF}PnARLm4<}YIhl61g{59<g+2vWl;i$xJ^Bz^FAeeAkv(xJ3X"
    "zDQZ7q!QQF!yoRp{`T>?B{>ajxUVf^<&ah}`a~dN+JiZ|r;WFU#WLqAO^hrlVg(izxp(nUJ0aXwieiYgV*p)a89LSU(lKZ7B6pVpe>PKC&G4Pv"
    "Qs;nvfR#&jhBII#7pBH+X1S)PK+?&z%|du!6A1iTi6fVo<)TjR(!*C?Dfr5I-Nc!BK}{YKHQ_a^o}cRy?=QDs($n833Y*Y8>>>S^dH^RntIb~F"
    "DK43!3?W=AIPRug2(fDqfSIsj@x*{>SMbX!LMcqvCd<a0f_yDS9oD6CvrgUglCeL#T<;2?09Y&0V6`S!C66Z2hgeKqDQZSM5sD<XRjNXd8oIOU"
    "SOSF6hXkg1&_wn4Si5zi295NopwF=@XM8mC66%VxaDlj1Xghi4Bx?IHfnt#V`lZapB6V%xrOo#=ld1yaq5;TEXZxHWrGeVI33lRCbM|}MElfNK"
    "XVY5+R2Y+tyAQIf%>>he2~925$Qv%gXb|qG8W4&vTz+fBXTOS3cE(sP7&&E@E?zv4IB9XLrKSLQx)#@9!L|V`dIa_uuGXFegnxtak+(R7lHjoU"
    "-z=v~lB}%5g^eixs%5d7u(e2(><6WMS$5i5B}(4<t4v*#itozI3Wj2+1>bTCDpe5|FvdG-lu$rPJc|;yvlVQkrdeVvG^&~tZU#$sO2!3>2b1*9"
    "od$%{od7sfmF7d1JF4=ujZ<o`sglvd60YPJSd?*68u%(EM4hlERtJrmnvha{1Zhc$ew-R|(XH&j0zk(*9^JXLB}eT)OIM9o=n^0a26{q`poC?6"
    "oa7OxiO%F|*8UL?09w+eg@AZc`0B7kII&jR1Kd$BHT>lr&3v&)t&L!b#8+6kiyylx*vl74&$I$>Nk_9EEBm5p+cI_70cvDQGtrzzFG5R6O~`2c"
    "zHuH>C+^l^)`;03KRUqhZWSk+eBDUi`~E~7exQ!wql-WXWo)Ki_&YEBooB}13G-y7klNFbJppnH0bP!hzytB=1aV+_5|2il(zq9O{H`o>f&_bb"
    "g$<A*S#g#l=SX+V4jm_V;v=8*PL@Ivl_w?6U~y^}sf)zgfhJ<ih|0l8-Q*`n)zSQ7xLpoKASAr8^8yLrYZ`J#KwXDakq~y^(|M4Oe(Nn2?r>B!"
    "#1F<6|2oj1(9A1Z=W-oGjUS~cp?g=b7{AsdoK-7Z<?ZEM0~2o9VkLBhDflU(Se0t(<615x7^K?dz?)ps3dO3lB$w3))Cy!Yr0YFUJc5aFmI)cd"
    "Rw5c5L9jaAx?&;tPVkrUf<6D1sw^tG6fr;Pz*KAj6B@(c@qm``enpiK-}C`mK#qGHSPLn<EK@0-ONIJg)vq3fz|-AfCNEf6n#NPR6pD`4yv0n9"
    "zAzUVVq9n^6q&!~ZfGdLqFdtz6#Ik^$HUspFdJSw6HJokn!gr9biqy=8A|J53jQW}9jT*FTt2m8_4MvrvdQSfhC-AUk#vo-RA&N$dG7-Xu=+~W"
    "$w;~>?*d@!>0tn!M)IF+jPo@Bcii(>GyTbwYWHD>)IGf?*9t~hl?76HZO$_|ELl%rMrG|LU6%;}$04Wy)1nM4yPg{mED;Ni0GD732J}6cxXO$T"
    "@!Cidp6NxmGf;sjU8FD^ZD7_SDnZIX1U1@rar`vvT|=y(<PwHyF}GueXvBGh!q;JvFFIg!gfl#;{-De1wS&5>Jec$nz%G|BvZ+6zY)W&4dxo+p"
    "QBA7QcspVgetRtpA^fdg8WmT<>XeOk(NZPcb+=MkqHfwMjy3@tgCS8kQ|;|(9F3|{s;X4hsc+e;O{T)G#hQY+jhkAyMR#-1lbCq2qEvL1_whGo"
    "4YwbLP_=LcqV%SEVO*u5$ccDDGAQCCNnn|{AG3oJ{1HBfJk(=;vgGc&DL^Dw#EZ@*<~LG<7GmaNgtsza?`{{-wO(P^1-PB#(c>(Dik~oPrLP*3"
    "t3XlHo)*GMB2{-?SjcQM$t=UBsvJ{}fH9gQy8xV(>>^3)#&z^il&*wzqb-x5|GFnHgE|~I7lh|CIgfB<L|Q10v<D7sihk2kOqr(Exb?VtB7CZA"
    "bcFIGtdi3(&jiysGwP-bP=-mT+nhgRT@#ap{u${u0u}aYl5J8r4;Uo#Z^sP*rI1bWx=oUJFNpYvR3jG0vJz0aJgN)5X!=3{Ar*CHEWy{wH>0#3"
    "I56Sm4yZ@vD$*neBhE?;DhX9=(u=J`{tw7RthCuK;n(!Tz)%=$A&aC!K0DkMb8b<A+{gAcL}w^2%dup*2RKuphb^$|ofae*TG^>M#)Vq}LI+@T"
    "G8S6waLOE*6Ukec#>H()sa>-rjkTga!2kuUmU|P_!a#aRA$z$~y|Rker^k^RD0_Ubt)I&)$Z1K{5<Oy<2c%W&-$oTqZgBYjWwpM#ISwP1#F|VG"
    "1B(soTmaIksZ6>Mxl+-Q-TC4+rguu%ZG|K^8XMbs<5K&W$ry!rt8|=|N5?sH5jV$%=EZL2ITYDGaM_-T-Hcjf+lMj)J7Wc#IR;0X%(bNMu*0s%"
    "AIqPHVMRnPrI(yiylG0v48&oab}_5wjPXj2Vy{&oPq-V4((&!XpfohKW;6sKnL)y^ewDF6P~xl~<m}=tDZ##{P&jB)qORBuXbQWCsiLl%6yYW~"
    "Ilas~9OFEI+1VMJX2h~-49)$O<CHiYah0D)!idMY>+ohPqch4cO*tKJk2)sFHY!{WUd|jjGk0<Dw(Z9yLG4jZeRdcjBAw!CJ%N}|0>K8hBJDHd"
    "a5Y6*M~1$^eL}Pn;$YSiq9U0H#8il)Wll`{03;Qu@;Uc<A@=LLt%{9MVv~Vx=3=IzJA5FvW(CofY8*{S@cSklZpi(bt$-eDxQ+U=X4b@A@uMS@"
    "a|wC$Ghz0CSfpT{WB=tTD7vbY7@a_&0xC_+9&`gErB<m`-a_I^cF3Y4w92>vfwV$hDIXVBI;m6wDg5`Sdczd6t8gzQ0~BVTBM&&cV^<PK*?E>#"
    "dXo?ce1TPh9yaw#M8cAw7A`^hOOcjd)l0TYO;s8|(<^d%6<@aiayOW#S%`=xNzG$JWi*g_g#sE5?rc-22EA?`MKUVf0<A!4cD18iD3&?W8|+5Q"
    "*nHn<^2zuq_M8oCh%=b2(^P_m314n@T1szLrEvDrQ@TzfKY%?-*Rn;dq#Da&R%r)fav|GPAdNAD0lz6^HN~dk6o;=Z@lC3JRKjUfN44q7mvW5L"
    "I{qq^@s8@h!^x_3CNWc5XS~;Q?4=%22$fn|#u96hsiTuat?hXjN%V6I&71107D(&C7b>V+`n8dmza|K8ZMAw6R8OjddEYWNRRqPs?~6CxNM&+R"
    "vU&zQGZt?gnfNdGpOOL8>Ji{VUd}9{SgAUW{xmX%e<b1&ff?2bLdYV53>plDKA{=K5+zP>n4=WDi?EYcN9VIlp?FK60<l8Gdt=aAK!>S9gJ8iZ"
    "^}j^=OP!Dup@P5wp3yfLV+?#%h3KgmHtB`?iYD@EsMpXfMf#vg6VWH=q8sq3TA&KObD^p*XF=Qi;?GPBFL4$m01;!4+2L5IM0d-Qq|9pR@(?>I"
    "9a5%hTePi5RHePH5By4m|9N}?AgVqmuT}&@D@?+xn)U1zb)zTKLnLyVlf#_6)2TnKs2Z}VW+v)o_G^ibBg3cbZa6ZER;Iez2pO?pyrd_rjfK`{"
    "02!+{SYQp9;|S8RH0b<6`yv#vpvLDC=H0p!sV8|rX`n^(Tp6aSzRY*94SZY4Mp>&@AYNN{!FoE2HP=gnXfGaGp7>F+a(IFT>llSM<fLiu>1BPR"
    "bPSL>5j&^*qm`=zu$q8;?u2snp}$9^VBPTT_pf(KRZ%O?hd@N{Vs+$g58$?NkaH!Xm{QSxz?IIqvu`wc5RUC!-8}+_iKABv*lj5>Cft6)dDzXp"
    "bdrT90${vzVLC}>NibTe+H@yzCD<F`P5*ulR2yUj7Ie}s>X#JEcv;0Y;EF8W_@#hmdv->AnQTq=(2hoHp9l~~epyuES5;uy7YVbCRJpxVP@!iT"
    "I8u8wSOx@^bjqRxAx~Sywb*KoGI!{eb3s%n)?SOMN~(%aSyJZ~pU=gUI(LZFp@mZ7{i<pb9mXs(u-z<sR-|bK`d^Er@D;(BkRs*GVm%aZp1Y?%"
    "V9~qvE6%5ylAitq!pT2N9XwSwxdadD$;&1?(xQ^!hwwg^BxEqe)$MSX!geSJo8<B=+S9DHim-ymzp7EF*m)Qc;3|{B3x97FQzJVC3A1n(kal(u"
    "lED!Bhy32(-&%bHeRds#iDC9|j!UtoeeHt}Mr=A((1&4*1r0J`BV8nNv$WT4y3A%1e0Vp>qlN>$70KpRpJcSIIw`d>i88xT-U_?`K_|Lw5ye#B"
    "5Z?tYDv)BK`4VE3b;7%llklX1f3ZP466RESU^`O9jSn>~7wFZjsBsroS?U*`4~}JI4fA>{r2yO!ksN7yEh)oOl_Zx?O3_+u^wnZ-7%Vg**~Z`f"
    "+j6tW>(+vc5*Hx}*K6FBO}mtz)~982Cw6CM1-6{jSKjA<uh_9KX%60NW)Z)TKyeR}t=@RP^?HH93)`bhx8<)Nf;FXXk;~`6qw>f4>?zQw3Zk{k"
    "qhn7|b0d*Gb%dNL!e?o+s9%OEMJYOJ!MC2J_7W~*0Qm?jP<3^JQ>yLdF(<6nZ7tMDYg{YUtR30WHYv>Q!yt0sY0V@kceD1Pa;0nwsWOcIva!@*"
    "%0N6!<2f#nqzUUjfJQq46sHoUVz*re-rY%lcmXu$m}yILKZ?nf6<feZj@5o++yvEfv4_`Rp!6Vsk3w?juELj)jUCYjkqf<&?KLfrX4Ns^chNP9"
    "lvu4xp5ml*nnhOZuOuHqN<A^CJvfJymXKdbOe#8*V5KrTSFM>D_7SO|_ZaN~;Vfv6U1HWjU-=cQ?vO=OR_bnQ(v?|w#N!*GCT_a0Wpq1UIjQkl"
    "wOJBM0B8I$(~ug`gP@RJpkgSA&Dy&c#`oM9C!p-=r0GJ_Ne;!u8*<_Ga(jWZa%i}s8^pV@K_9OV8sF=Spk6_-Nc31`T$U`##446|8Tt$zh!S}#"
    "RS~LsqfI8h3h@;%#&V69uI}mJ@nRvIzz1g6G56+MUv{!ZAWX+rGEZ!Fdn#xEQnqAtvS?K@#aWkxu;*#lku+Tbv7%y=aSI%&{p-1}xSELu8aeCx"
    "QX&|XLu5lJ<*Is?qxpTuR60rkqAzl)VktOs5s|Q0)xjyR*U-l5C^E_f4UE8r&d@;DC9FP@T-k`!vO$HshN}dh)+xDp@l$~}a5{izs+tO*Aq@1("
    "GM);9dKS%nTv^Wb!FdfBVC%qL8YY^7OBPFYr_Ikkn1SOOT(7<Y^?u_wM_eLEvGGq8`_&F3%>*lcemEAHB1r&_*IOcbez9!MVwpkFpag)=F$nu)"
    "a1RoO!~27lhK$e<l{`N5Mwr~kt<C|jYz~^-eKmbSfZmffYGj-HI6Z6*?0d%+=?!qpJ*ZEQ5x4FSpZ(3#d$xU$^61&EN4}zPszv1b#ru%FS8r)u"
    ";X`ez3d0}{%y_CU<1;Nv-K&Ca8Yfi7^7`uS)~1=`vBiHueo?H{k?Mv+pw?H4Z#kOoLEj~O_>dlWr5d+5l<Ue+_UJ=Xi@*Ipgglfi"
)
_V12_SYOUYA_SCHEDULE = json.loads(
    zlib.decompress(base64.b85decode(_V12_SYOUYA_SCHEDULE_B85)).decode()
)

# v13 robust core: senkin13's modal trajectory (8/8 train replays),
# sourced from episode 89634061.  Opponent adaptation is applied only to
# compatible market-order sequencing, never by splicing movement routes.
_V13_SENKIN_SCHEDULE_B85 = (
    'c-rk<O>Z1oa{Mnm^Pv7BDc?9!uOuu-6ewzm^?(=*;9V?WtPf+~4F7j)huzg(m64H=`Cc`t8QmKE=z8Ck880I8r~f_s`!B!#^KZYN'
    '{o7AxpRPZDK6^Yr`^PW;^&kKJ^#@-+{_~e#|MPGE^Y!yjXYW7UZNL8Z=)(_R{`&Lv#}7YV-<+MFy}5ljJ74U7{CT^5`}K!EZf|Zs'
    'o}FJze*Ex$dwswA@#pQ$&EZE2`=b^5tH=L4KW_OCUq0Nt{rPMA@4x)kwxJ6@ojq(n-~ZOykGFUC@6R5`o%&a!KHc5E{qp91(yl}='
    'cmKATw(8S|H-G-}>FB?Xnzd`q`SGWxrV0&QdhMDv;O6?xcK6%S)2HKAYQ@U5;`96M_7iHyejpC*KWfb9+b_FE+h$FEBD89Kn7m0V'
    '{`9Ze8a;VDLCf(tY_E3<2Mx%0Jr46>TH_DJFjmJ6dUI{2W49^yAJpX=Y?%G`!xi~;*?hbob}wp<(27N^72_rQb?~q6w|CVxEb(#V'
    '?vtlE!80<PBZuYs^t;+vtm4&qco3Tq{a6F7SWa89>n_?O$770SW!GG3S|(53jV)Y^!?+(lJUzVfp#4BT{eJYs-T0%yc88yx3Fd9E'
    'A2T?^hXFnMq#neJcs#)<ZsX(a^ZniR!w=iLyT6{DUna(Kx`~w`oqV0p?Mq>VhgpRKj22R`LF~}l6N0`uoR^k9xWi-Y7!D7ngE{Wu'
    'S{TLY*0WDYZOgUr9stKJ-x<N~<EwSj75fu=7VGO&8ey<JP0x>?m58u%L6aUm@yHrPNc;gjNE~+Ao7<b4?VJ0b|Fpfk|8Vo+-$zR#'
    '^*&s+wh6qX{IDK3tvCk3V9fCB!&ipS99lOVM<6uFbsRr(a?Yw@b0!pidw2V(@Q7jgAGO$?17J%HoB#dw-Cw-Or<4^eGKcQ)^)_7S'
    '@MPBS!`FK+m{Ie>gK>X|@?K8fETwLmPys#KcHwBRDzmFcdaQScU^jXIn=6p5R{F5p#yIn_odCal`{7+}B~B49*nz_X!K1_8*+&e='
    '*6|+i{Sev@Foi=~$WwkBX4n%jP4;)_6emwRj848=EhCp*e0?4<43{0Z@BzZSq`n@$y;7iF_-)Jn0jC_;ikQ%h;i!%tK7WKNLo2_l'
    '(3QekJz`fdA6~4Lc=RFyeS8!oe?Zd!GDa)|NG}nG_~2Q98YDWTe0Vxrdq>0s5CHGIVkmq_rR)e!-&U0l(pY$SIEo`DFRWB7d}ul7'
    'AGqnMz6u$3Z<AE1Z_}5A0XuEfJbc?BX|+$HkE{mGAP)2v5AW>P^Y`vH`OHzKOv2BWNPV_obC{~xvW?+?hn$Z-;pwkxPnf?CUBYEO'
    'aJ7MBfSqS!)=@wj1g{FBbaD*!dxR<m`Nx;911si)VJx{a*)?bL*cFpyacw@Pb^=@QrbC}lU<S6+RS6=c%e4t#V+bCL`|M>{d~y}h'
    'VA9bpu`j&^e37B=(mAVhA@LKWgCpWZzgb8OR+khKXLu`i;Z%A-LR|(tK3}M-j~+ZlJ9hNj3vn4KgX56|1J`2TLg$W?k51t)#Jy7y'
    'u(=NDiQF!p5xISV5bX*B%;V5%{l|%kDKT;Oc()(bLhq--sB466k53uza}1$M@FqIDVs7~OE@g%J@dD-5>l`@06S%I8f_%ys0<4Fp'
    'AASU{OGlkP=1wm0fC%J57%%Obdh`S*CI^4$w$}}TeBzuB<a>)ZUZjkDi0{iycaIn&(aPWy4d?p;c2140!5(XW0!AV?rgpjW3@dXV'
    'X2W#~^@IG&=IaT{i2Hr^L+caTI>C4W#ZC-?$NlY(*Y~%Gwe4pBmg@#0TJeg+9BnYFW!a7Uqi*R9c&T*6jwb=+r2`9WP83creIi68'
    'B6|s#av!DHe1Y|9roh_1)K3^zTRC27Hftj@>|CdrOf^XET2hTU9E4LPC&CXkNoQjN4zj_3>X|q-wQL0J5B-Lu!om*G=4yv|-r*|{'
    '5odRtq2xL^RT5%$d8aN;$@tF8HqSu<F*FFydv)xA1Q8Pzr%dKWI?mv3%#QC6O$>9HB9gXVUVw-BFk}TOV%IdR6{RkN6oOp&fgWcm'
    'JqZPO1liMeh45|Hy8@jD+)iLup57&Z_r7)}4#+c-moHl(aH!puz|y%Sb4|Ev=JKE#69@4)cu}_o<N#ev#OM<BBq6sy-qN76yghxc'
    '|G|Jfm?lwitl<+bA2ZPy0Oi6Yq~Q*RoE4l2p#zUBgzzEt$R$8j<r7dF-7$nIafK@`bvEJna*?oH01RM{dr~rcU}|zokeUE~xWBiz'
    'H=w(8|A0Jc=;+jt!S*<Sqrj61Cj+D%8J`k!le@~CrIcYaX)9UI%-kv|htvDMaPZ2@+)A*x2_;9s_C;?qyZ#T5_Krq{9y*18JINXt'
    ';%s*Tf$)Kw)A&xY(iXxRsjFAOlP&2d`DC#46eGB%xPH|l#Oo6AU-;1X&GpB(J;HwmWlFY2=Q-FOX)ce~@j7d!SGtA}k^j;qMKRSt'
    '5syjD{MNST8!@dWc_%SLIzl<^cHC++nZWjf5h?y&G8oI)mVg8TGKt+kt6X`pJcjU$*mA06HVS{?oN_NF)SCLMQFFGlK&tSgs#w;J'
    '^6;`|kB`Yj9#R%$P6X=}u40k{)x#Wz0sJ82$&a8nQm9dAe{TiOc#lDn=u9+48CIV4S4*w4RSk3iqk$OP4OVx;n4#Q+1n$7muy7tE'
    'A8HfpybYd`HqfadW6?52t6IBUYCpaFs*Dqnzeue?JSW{Ba=`=sAhs*EUBNYa)7{x1TsdgSs+J9<Q^y`jWR!?4J0zEo7pq#GPZf$i'
    'hE~iPhxbtBeo9Ux_fX=8n?LWCRCMjvoLWN0GQRCmdPdONV`7q<>K7ALljrepL12%$){*@gZ8~oXfc3+V7%OiA8<0h}s5sS&lOuA~'
    '3h+YYOO#)Uiy{xu<^XmfF$KImAKU6IoEN|q*ccy}m{6+NIt0m&@YaszO^0bFEIv=Xaage|ErP4~5PWm-k3Jion8$T7IPOVI&;@`;'
    'y3q_x0BamHiaJ=?fG{VnS|k94;C09tr)DQi7sygdi-NJ1Xs~u|hi`Oi_!(b42TirZ4BiPEj)Y-3a8>8Nq|<E;1HGuh^zeYhxTx`T'
    'QQJ*O!p`%EV}VhQ$pUv%R@h#AOPO=M;HMtwk!xTT+$HaMK{;Lnd~URyHMFpzs-qYVJad^To0)zO7Yt^9w*_B6wqa1N6$!Q$9-nHt'
    'YZDNxM4P`rwPp8p=phs`VGe(`0ecoi;&wy9SgT;l;<6J!VV6|fMPPJ;-Rg?$huN^kQumAMZdPraSO9-$P&4pt#%83k=ZkLm5GPW5'
    'T;a4=M*dE{0bU8FlQ%Q!`vHHsc9O#m0!G+wz#e89xlSChDxn;PU^C0(9f~9P{mET0Vo5B@9+=l6!o0w|IPasd53KG>LD&y$qPXoE'
    '=-qyzhL(z<e}#<#mUH0R0?M02VJkHmfGyvouB)jd7sEV2Dmxx@&Gn>d;CV`5!?ke(69{Pio|!FkMggIszO*=JL?U17*fSY>Dwm0d'
    'UZDTSg!Dv&O0!-5hP7Qm+Z|TkscnGQrISZ==;UqB5WX0Jf>O!6`mG#Ct=-_Cmsu)X!7UzYnDb>OqIHs}W)04DN(G`v3VHb!@e#Dr'
    'C@jJfZ8Q3vj%RJWIDL^xzvC<SMd~f02sr}KDOuZ-8VtF$&IA08cpF#8wWHs>$QNnDJ(e2oarpD^n1_UU9RH9d#HB92>d%4+DLrXX'
    'v`(051O+mS3`8+e#~`nX6n<{iXjm=<gg7QLvQ!u#%xgdFV=Is(B!P!cBgs#}LRnFE>?3iAJ|*C)C?oqJF@>0FP}xX^8dr$c7*Ir{'
    ')F@aK(y4y-mAWr0-g|a$j8oPoxjSetE|=uzJJEQSlu9gLpq>Cx$yA?$R7@#pARBHD8JA=FtBSZM#P@hggg!CKO!2~%CApl+0C<tf'
    'WMU`izf^VZ)SKDtVOBTX+{^MAVE!ii;-x-G|F!4xd5)dCb-OhnM4{GhECL3*Ovas;qK~O2Glc~mAZ^S_+=F~Qp-3^l6AN>>M_eKJ'
    '-p*7t_NYt(2J)m=7lANM%$oL<ppXONsOqf4)nk&x5k&{gBaV5UGF6=@i!z5v#$g7ji-5&|wAKJLE8wr=BdlHXv;U&?OyZt4ux3>t'
    'sVGJ^FAl`nygU#Ge9>=9eA(XHs}sRFMbZin9Hmcl5k4ruG*ytNE$vEI;Yozlr-p=Z&$TbT5S&KZ0Ud_pKoCK-_nwQ$vMefpWVlDE'
    'bFL{N+GmH~x&|5uqHLN@ab?`;)i?+$jMn>Lmcp)XEOJOmMX9`-A!yvZka}A%KC-OZpd@^zG65I3<mQ|?RXQAuaG*8sh5*N+-s<)g'
    'YGWXPQc=Y8F+AD?Xdds~3V0MT+*x^4bk-5!9jmd`3r4iSi%9C@td*GEbdli&u?<L#`a|+$nppwGcI~o7kkfHQ&&^e{<O}5hWJe68'
    '*=V!G0M4d%GZ9T<k%Y6CmKMbzyH+MbLl9~62oNL|>npX~zEhwRtIWG~ozjXNC|1;qhot~ma-r|ETx{n{@YtO*<3J&c1U@s3929t_'
    'A8OHjoy@Z3lagqXZ7V`D{n50JW~&&2LARQb=Ai*~G1UP#%}yqIl`hS;v&s0VYGFbEmf<G~4N5LkoC$l?Vh!{$k~v9qvJhK_xB!Rk'
    '28hceY{gDX3qvS;of2XNrRqeRLX>^5bT-LC->-i&ExUeXj1j;9+kHdQUr2swpi+nRn0#b|N-Nm)zAJ<&7XKv-bUU_^UrC}}_I8gc'
    'D%@++2n2SQH}R`_EtQd_bLJ@W0D&Z2`E~(0N8+dtg5hnL6@*I313JoX_gUVJpB>b+Ey)FrQ5&p_LxmQ#EHGysv}&`fq$an#=VBg6'
    'hu>_D-J0gUr3u^!Xd^PYcs>{05fFfD^z!&;`|x%B*j7=yVg5Sy+AUdTI^#?oFi|egrd^>2u$C-I=d`w600XT7e;DrPb~h6jMFQS#'
    'GT?0#a8Rlht7W^z1>W&)vjt~;rAT#UaiLbyj6GIqx86%P%Vzp`&lF&z_3s8Xdi_U0jS3X3&FRpjlJ86bOzKg2lcg1UJg(jBlJb7>'
    '^&A0<5*Y-g#7H!qdYys9vH*j}#yWTAG?x&~6rKV1@$4F#u^7PcWDv1M480J50)QAG;<2lL{L(GFnbOe@YQwZ!39y(_r}+2u(dEl7'
    ')ejPviro=+0K;tidF7+6P@0s@KnHFlkphag2O6G-T$?~%P&KIGxuI)ALskguV5W#^e4Q-`kOB*B24+&9)A~B0+B|ecufLw9?7tEY'
    'F$Ra1-|u8%_8q{<A9GE_g9N|=nr7C{M5x-V=2kimb5*O@l;+Mbq6a7NWHfPOZOkHr7>ZnFI)ei=HLT(G`Sbe1z(2dkrm$Aj6Kk&<'
    '3A&0?cLf|*(sy0~?+fk8;1e;$A^+L9J(n3k5gma9Nu!E1@<P;DC4Et=%RJz)OxDXNqy{rUJ-We6BTO|j?<WBXR6r~9rZ}m<tYCTs'
    'S6a6CR98_M#?lI8d+rFNi_0E#AmOm%x9{GirJSlK62N{KnqtL4y~JjI9S~Q}<b9THpJx`GNo*)E$bpgJLG?7pvg;#*v5QF(8rf5$'
    'MuD=oVVcb;2s3o16pQ-lD^HCLf)pkS7wPV202jD=w&y^>1zQo!03;NB0)IwjFp73BCTG}XmbJLxpDZGzyH9ybYg$9;92O6p^fN>B'
    '46H;#RG3<%K2+pz5uHqP#iBS=j1PC?42rPg)+N#EH)QtEw8A?Ie+++)${obiU7l!;xE)WDjG#IZ*qw~L0oa3pE5Vp8GA1|f%PZBl'
    '$&xw|sgB65;AZ7#sBS^7Y(qBwpfAidhZe(%1-}3>2mJ5!U@|!@L85aFwd^A6TLl0Rr1XlROSW=>snx|}qWyNXEa#PZ3yJ*Acr~Q`'
    'geE+YF4jR6Y1-<$G|fkzfO}Oxl2N6|^m1OjCg^X0RrH*|O`*CplT+l#Lw(d}xL>R^5y+&;O>F^|p*O`3s$j8_CbxZO9}W>^1+j1%'
    'd(^Tu70v`pe<?i1Xj|02rUJJt>uj26=7FJ)iiL@+qspRDDoyKd^Ws&OZ=agV*TA7c!+eerMe~<&ib$HH#D{g1tk+l(=cc?>!Izr|'
    'CN-~f300T^Ij>Ts+E}S}(pve}B(nh#0Cf%u%<3DJOTFO_AGZEh^w}Ia31)akSdPdcGh%dyKq<3BV07!01Y#SI%QD`0h-d*Er>gbh'
    '!Gv)4A`1M`jsZxlbVO?4A9pJPe>NsAf<2vE)*P!3FmK5rZvuGa!rPdXE7yD!7&GhwVV&|zBwIk>ph}#yDdg4@AvvlKDU_j7-?mL)'
    'Nv<Z=a`}e`P<Y9rXAo(LGdN(8m`8Q-*b$v5*a7Kj^fv*v(CqD$=082)7M-nTZ`inV1TB^z68OUfg9CI*eh_<{4CQIvl_W63DvuMh'
    'pofCD6TSb>F&K!tOIA-grQMo}4V223I(4~A&hqT`T+bUfaX$c@mT0hA-KoL>Ac2iotXnCMMWp&g(%T}%fKfw#R!>O)N|K~8$Jc@&'
    'JEB4&a3_j;nagX$%FB+YHe;`OuBW}li@cOLH_%F*LW#O@OavGt)qas|u>e{djB4{m%~h#DuV`2gY5ah5qBMA2cWO?YbIyKG+gpie'
    '<79fP5Dg=baqB#G$*NJec4K>`*gi33s0B26|3s_~qAFFBJ@HM=uetalsRE(-;#s>lCaXkMroS`_mU@~q*YpG30G#EVHalR&wV^h8'
    '?3IJvR&xoLJpBm&hH=&oVGkwSIf<r8GGPu^F{1seX1jd~G;uYP{h$=nnst&u6zHwC%G5<!czqrifT5Nj%ZaU2HC;t^T$3}Q$dS1A'
    'Brb6)u*RY!Wn#oPDzFpo6-$Of#s`T<jr3}shIIa2W|4w`Z=xWZomI6b*|gVq$);frH*K|uy<WzEGI=UW=SAk^V)wO@nulix6@P!H'
    '##wZsJJ1KvfsaRbDq~^ga4*2ZcY=IUH#bg;K>iC<h8iczv5%$fkcoG9s?%e|LqZuBpj*;4hX9D?ZY+-15vKr48--iZrRJ!5GIN@n'
    'Pu;XPNWsdAZ_ENrJzP5MEe_OaTHP|yXUuMhu6UjWC#{Gl?N&pL>LxqkSTJ~ON3%|G+>odCz8@Y8DDM7Yf=OpaW-!W3Y!zdieC0&m'
    '`?+*h%jc6>ty2)j`a5yxn<5T9FB>RKrIj*aFHw30s4@hFd6{$|h)yR+1WF~=Htvr`!_s&dGLUo}mwkQi-7Rt`Da)@QSsz|#12{=m'
    '!sW<2(v7o2*U6pl$WFYIMUh1HNeMz&4B7?$l2|>^lZ+W#IY6qL>cH4!zwnhh5}NxAx7wjNg@jWkHBcj0)mJ5tXH`HcdsH+gkpKeF'
    '-JsD4B;Mqr-+F7W;H@MW(FYTNe;o*9Xqpzi_T(CW8vRO>e2e05umLu;yOS8=)k-&c2ShVrHDRDF)(uBcg`ZBQN?!+AH8~eYH@-r3'
    'CM}<3#qqQX6b+eqJb*FUN02g3Lm^`r=nRdn6TfhlDWDH^39LiVMmpG1?Y`qyUp=NOaY`;o%&<DJE+cHLvLGg+2(=?Lfg-U4(sV&&'
    'NIhbir$INv$^~9mbCQE9C{3^8QoMTGOkAMu{y2FdL|??Fc6St=jd_Ed9_%gVfkXTa?ernb+1wosg=Ta^-hh^$a1lAJNe(mrwKKt_'
    'ajuta5ug!Vy^)Qz4!PiOlGl+s`os)WtIkd@%_Rem*}Se*1~yJToe2o$y${2Rl|rIEOw#Rn7wB8h<N|;-k_>HQG%y42VW!1Z&RJQr'
    'GRo8`_c4al4ZbJ+3PxTP9a5cd&T=@c*G>>gWlhKHJfM9O{EZ_}0i;DqUUub&8Q*1=Z6`v`5x5fU;Tmyp%C@;G>eMBjn_i4MhbX*$'
    'tcfQnBuCqvx5A2mI!5L|)H&K6ag?PNKPCE?0%PuYlUzI|fHTxwrFd7Iz(`b~OLJYY$%xbFVAI*j(75P@R70t%XOnTQem63%#fz13'
    'X+C!I!)qtkY>6sXJ)mmopJ|;1E`-0;OQGU|UA6pmGmDTb;U>J5$|udMzGKJ-!>({{+uOrA8dasFR;m0{-|||kOp#rSP6e?Ux6W|u'
    '?uN+#DyO4d9E;g2tFuKnM0=$znS4)lnnU1PxL;BF7fz4QYZs_eayFlkHi{rj6167A(CkbFe}s=L4?3A1LacO1f=v{N(t>a=I@g#Z'
    'O3o*SOlDj#N`?_pefzN!^rl4n3t&RWM#xzbVxS2#NWJmC=uIwJMeT-aZn&W>44GUe?PYLQ{)S&GzQ>7`Nx$|<H8Jh94p2g<%O$iP'
    'ZB+yVK<tQNM^+j1!-0@N;6G6e3D;Lj!=Db3Rna{=iaw+J9UhrYpptgKwAdY+Ro0+rPS2uK&m($T&dsM`;?O#!CJ)LujOW#}@M;8V'
    '>kF+6&Pg>XbOwx(`L~w@+@z33@%l_ud^<Red3E+My%t$UET&|&t8!UR7iQ7;um_P1HE}E<%*nTwv_v>;;KlK%M{0@cj9!BHGch0|'
    'l)i~?x7|M2zI(Sj7e|p!(Gw|P8nLQv4+&qW->eS%l(C}vKszB7t8h`W+&~mrbtp$hp;-<m!`%~+2AcPe?%ft-0$Qc5IC6zs1OfnH'
    'TQllfY^BQ0pC{Mq3!w8#T}6j!S={uL1~*$zSu0T#jAOuq*}JWVEksgH3>32HfvTugWIvPH;(?_O&mM_v>nH09lG<1!D)5-9u-3UZ'
    'am}xq5`q+%nbv9&<;S`g4<nPrs!k95ijDRZ9EmhL^2?&5`QR(%Bt=xk8Z4y6(U{y8K+m-p7^02EXy@9Dq=i!>#9{45J<sNRvzc8~'
    'HG|EKtg71d=jsGSxDT|o7gjUtK=V0WA#xvD5&V}GWa#vcIhpH7-S3Cpj6auu4nwMlC`&J}rFiF*Kp+VDIPGHI(isz&9ARIp(w?wm'
    '7RBh>(*Qy=7iW9~Ak0DXvmB796=HYpb*amYx1<Csp+b?P%Myphc0kkdMU)kF-K3Z|!O7|6;NckOvC_^~-ZVFs{bnc%pd6>fZHa3M'
    'MUq84&dG8aig5%}xN12aBMZ|U)Nv7!33scuEe#irmsUp>(_O5{ZToRyRC4RiWpkDk!Sg?{T-=jOK><ig!05oaq<yZGT~E0k++jqk'
    'mJX&z5*two5fe3vE<7>)1L%5KNq48^fX8G@U|l{YT;w0NDr`a-PX_0is+Wo;_kr}Am2{Jet;Y&AuNLh(vy3P_9mq@l!W4F}38&K|'
    '#O(m9r7Ofc2{84%rN7qwHDf}0-rMu%f|#w(s3ZfSOu^^J{>uw+V-BTcRi2Md0nu=pR9Dgcjg+6I)^rQ$%*L;;bF*o|7Fw#^U`txT'
    'vXlu8D<M@X1r`2#RD5C#1q#!$F1fcb?;m-<*<HUQMN(d7vcWDZgeT!0_|B{k(4m)Q5>^Ver3sR4itBVTr=j_^R{4kC#0M0BYP~pj'
    '-+7vdhzFBYW%jMK9IA9Ul(bD@B{f$d_ZrIaGNrlP1LbP5td!oG7c1wSJIWm3MO~;nMK=sH4hzexGn|h_wo7R&Je4e1zVOXx=dScx'
    'R?3W*=6xyDhY64)K$4{k+hSl+N$GGd+v>tGax)-Ig*2(y$DHE(wR3615@7|5ruDKCE}}ZRPFH)4k((5^NoCBbgS0opO+8xIImVeA'
    'jo1M`qBkm~!3^LiW@wk0&e92@HvK%(B)Yyj-(4<pz)abLJ1&agsjq{vX#~FaDH?JwmNjq*Z;Z=sTr&{w;6^UKMfzFZz&jQ?pG12Y'
    '{7=a?>N)JadBL@acBP6zq?O$Y@#%u<6kDuQqMwEH7_Jwph(ceAL}`>w-A@<CA4-wF2=i!lmlm=_Rv#X`z$11XgTw;TOcl}tOGv3$'
    'CX!?lXr2@BUu9uF;8M>x9gJ`WzN*3#y-3x>&DhQ*uyZw5s}Y7AKPyF0p@}BZC+OW95VR&OUIu89>nH1XEYvjSd~TZ~hD_UeskI=U'
    'kLZ7r$qotYg=-7W)M9URjp^a!p~XDK(hpW~-MQ#^IAT5RgofZ(;=Mp2q-nU7VXQ!{<O(mX7A`t1&)-c|&SIZT50U6;b{11^Py_h1'
    'j*)U!L=HJ=Gf$#2H@BxVVE`7RKxZuBjld6!tf!TV8XSI%Eo=n1SiPqLGiS~gNXQBxaczDY8ZOk@uwANQ+u9ujbs`Ul3bYWPE7J_s'
    'neB;bxO$h~UELFy;jioOK3!!R+*K=3S(fF_;M^toJG>-voQR?^mTt%_%jog@cvI;>A9WsfPUXtGp^Ik~z|I7CllTx3N?C_`c*D2v'
    'Us#kif@1z8bYJKHFr^TAO9KQg9OPW3DJD_0A8-kE?&KRy9>iSx$opjNG;s|}VYMw4%!G?aI1dj~JDp@riU9rYT=!1WR}$D&DqP)3'
    'RSEV+c%i<V1J&^uW$eWw#r1m!=CQ1T3vfl2uJuw7u{}E@f=af$duRx(wNC_cBg-r*&*N3_&c}X*o02FD$mB)&B#VDUl~N*0Bh^oX'
    'l|ryWr_4$a6$yH`iq|^>_(b=rCcPo0(MR<wRq3ZJj&tkR=R!`M*+VMfLh<l!RV8$W7xh7<jAct}6)9Bw776%VdG-4eymCtY;x6fu'
    'kMQv4jB@cbAFulgAFo_0)N=|SH~oc=^B2qOg7=(C^*9F;YW1zF9vg^JsqP8yZAsV#qg~xYSB80#a3iHYleC^ib(+0a5n=H7RyBeY'
    'JNzQTo658Fqw1$y!cDH;_*QX0vh$QMFlW(eXR9F@Jh6YsZ|42|SJZ&LN-#kfLxOqBIcCS2!Zo=Z9p4y23-MgxN#!4gSQfO$go|{Q'
    'Naxa?z3EDyO;Fg=v>!DbNT>)#p!zMNl}5!^yKz3Z@w-0s>@s;P-1!T#&!Ql*r4NXWf|d$Mt<Wq~2&z2bAcG8F9+7*zER9)CF(iSc'
    '^+0O7@sXyL1ib<oH4Cl{r=(HYUBv3*bIIY4tp8q4=LFQF;-xo0P9pjv&B7%~xKya}xN~*!sHQiQ%T4F3=bs>nWGN=PM7ifHyF6iZ'
    'adqiZiF10oJh48le9Pu@iU391?y3Ln8;t5g0TL#k0DyX!?ITC}f=ZgF;!?Q?+RNlptu?aIE)267%1f_<c#$)Me=$6&idgNHG=<A&'
    '=2THXB9T+|>`W@ca%pm`U(Z6IqQo7w)LhRZe+hRmfMtZGsaibUR+Tz`d1MI-bz4hB(jwPNIcrBav`uPqYjMajQPYnBsU^0QyMOy|'
    'zEYlqRPIH8*;rLEMGy?LdJYq$*~8<-a+xssGjb4`HxR1D!?qRa#b`W1f~e13fXF$v+M3QUK(oO9wFRV^FP>IBj`0|Dk3|u2skNV<'
    'B2>TUV-2}OUO3+*FoVsBqSM<`5<JhSlB2f9_ZrqZyEP2BBD?yyWg~4yakT~8xHQXx9SnP>v?l}hgOe=+i!!2j+XqJJidQ!ykXdi>'
    '4D2QGvnK1~DpTYSw0KybHas6%5skLgT)Oo@P!1YB%-e8H7~Idnu-04p0*uoWnYm(yl+DZ>-J(~{qvq$;u$QXjl1{yVmM5S*HNq1?'
    ';l4mlp+ht4p4|)c2X49(5QBA!d7<efN8>6IxrRJrftGnox-F3IH}3`ueT<K2wxBPIdR50$csg0Ai<MoUXXpv@h?0XVB^A1f(pZ!g'
    'f;?c1<tj0y+6pwf)v6ha#drcsnL0mBawg;14{j2IgIYLfnc@kQC&+ezt5e7j-R;JsGfIo6Dek;f6d_+OM#K!nzlzPtEqbN)BenTf'
    'wav#RSTt^F(+s<tqco6dVUlK!FLU%L35mYk1=CFKyQFKHy?PK%DL+x<({!W>Bg@zsG=S1CF&#THePp>X6N!B>=-ZxvD%544VJdls'
    '@#8_#M|oGO0Qwj%2*7(O$-1h^q}K+E4)2s=Cd#E3LIGmoY8enEVDcJRbFuV!-2Cvt6N=|W2C3I>6Vw-`J`nf~6W1nE3IwE%5bfO3'
    'thxl-s!e)yGWDAHy-TCMR&$vgjvt6wv{e%2=m*4CwOgbqyVxAqPv<iYMWLbV;U#VLtKn%l_A<N>uyy+$39?XoMW9)lJ8=K*TaJ+~'
    ')LU?aX4KXs#vrT5vf1&Lu{R=iBz&4J!~M(%0I&(%$LvRh+}T(fYuI@(tK?=SxTl)(B!uNSWeX_7zW=AA3wlf64V(^a*<V^cI?6lc'
    'E2l}DGmiF%L(VVYl>z6LP2phxh~RM}<a;o7IC>xA$nF(g2d-CfZ3!fd?t*xDvQQ}RWP0Y@T)){`^M>Pd0RIK~MX^E(+1F$nXNmRj'
    '#6p2et`{tTNFDjcQYt_GzQ|445Y$XJTIz?JcK@Z6?-1DI@)gzew*K+|0jwJtdj'
)
_V13_SENKIN_SCHEDULE = json.loads(
    zlib.decompress(base64.b85decode(_V13_SENKIN_SCHEDULE_B85)).decode()
)

def _spread_animals(cows, sheep):
    total = min(len(ANIMAL_SITES), max(0, int(cows)) + max(0, int(sheep)))
    sheep = min(max(0, int(sheep)), total)
    plan = {}
    sheep_used = 0
    for i, pos in enumerate(ANIMAL_SITES[:total]):
        target_sheep = round((i + 1) * sheep / total) if total else 0
        animal = "SHEEP" if target_sheep > sheep_used else "COW"
        sheep_used += animal == "SHEEP"
        plan[pos] = animal
    return plan


def _build_animal_plan(cows, sheep):
    """Build a target herd while allowing a distinct four-animal opening."""
    cows = max(0, int(cows))
    sheep = max(0, int(sheep))
    total = min(len(ANIMAL_SITES), cows + sheep)
    opening_cows = STRATEGY.get("opening_cows")
    opening_sheep = STRATEGY.get("opening_sheep")
    if opening_cows is None or opening_sheep is None:
        return _spread_animals(cows, sheep)
    opening_total = min(4, total, max(0, int(opening_cows)) + max(0, int(opening_sheep)))
    opening_sheep = min(max(0, int(opening_sheep)), opening_total, sheep)
    opening_cows = min(max(0, int(opening_cows)), opening_total - opening_sheep, cows)
    opening_total = opening_cows + opening_sheep
    plan = dict(list(_spread_animals(opening_cows, opening_sheep).items())[:opening_total])
    remaining_total = total - opening_total
    remaining_sheep = min(max(0, sheep - opening_sheep), remaining_total)
    sheep_used = 0
    for i, pos in enumerate(ANIMAL_SITES[opening_total:opening_total + remaining_total]):
        target_sheep = round((i + 1) * remaining_sheep / remaining_total) if remaining_total else 0
        animal = "SHEEP" if target_sheep > sheep_used else "COW"
        sheep_used += animal == "SHEEP"
        plan[pos] = animal
    return plan


def _build_opening_plan(wheat, melons, animal_plan, carrots=2):
    """Build a 21-tile NW opening with long crops nearest the shed."""
    blocked = set(list(animal_plan)[:4])
    slots = [(x, y) for y in range(5) for x in range(5) if (x, y) not in blocked]
    slots.sort(key=lambda p: (abs(p[0] - 4) + abs(p[1] - 4), p[1], p[0]))
    melons = min(max(0, int(melons)), len(slots))
    plan = {pos: "MELON" for pos in slots[:melons]}
    remaining = slots[melons:]
    carrots = min(max(0, int(carrots)), max(0, len(remaining) - int(wheat)))
    for pos in remaining[:carrots]:
        plan[pos] = "CARROT"
    for pos in remaining[carrots:carrots + max(0, int(wheat))]:
        plan[pos] = "WHEAT"
    return plan


def _build_crop_plan(strawberries, animal_plan, tomatoes=0):
    # Melons retain their proven two-cycle opening sites.  Every other usable
    # tile becomes a candidate strawberry site, prioritized near the shed.
    plan = {pos: crop for pos, crop in OPENING_CROP_PLAN.items() if crop == "MELON"}
    opening_strawberries = [pos for pos, crop in OPENING_CROP_PLAN.items() if crop == "STRAWBERRY"]
    candidates = [
        (x, y)
        for y in range(10)
        for x in range(10)
        if ((x < 5 and y < 5) or (x >= 5 and y < 5) or (x < 5 and y >= 5))
        and (x, y) not in animal_plan
        and (x, y) not in plan
    ]
    candidates.sort(
        key=lambda p: (
            0 if p in opening_strawberries else 1,
            abs(p[0] - 4.5) + abs(p[1] - 4.5),
            p[1],
            p[0],
        )
    )
    for pos in candidates[:max(0, int(strawberries))]:
        plan[pos] = "STRAWBERRY"
    tomato_start = max(0, int(strawberries))
    for pos in candidates[tomato_start:tomato_start + max(0, int(tomatoes))]:
        plan[pos] = "TOMATO"
    return plan


def configure_strategy(overrides=None):
    """Configure one module instance for local HPO; submission uses defaults."""
    global STRATEGY, ANIMAL_PLAN, CROP_PLAN, FIELD_PLAN, OPENING_CROP_PLAN
    global ADAPTIVE_ANIMAL_PLANS, ADAPTIVE_CROP_PLANS, EXPERT_PROFILES
    global _OPPONENT_STYLE, _EXPERT_EVIDENCE, _MARKET_ANIMAL_SHARE, _PLAN_CACHE
    global _V11_SELECTED_RADIANT_VARIANT
    global _V13_MARKET_MODE, _V13_MARKET_CONFIDENCE, _V13_MARKET_LOCK_UNTIL
    global _V14_MARKET_MODE, _V14_MARKET_CONFIDENCE, _V14_MARKET_LOCK_UNTIL
    STRATEGY = dict(DEFAULT_STRATEGY)
    if overrides:
        STRATEGY.update(overrides)
    ANIMAL_PLAN = _build_animal_plan(STRATEGY["cows"], STRATEGY["sheep"])
    OPENING_CROP_PLAN = _build_opening_plan(
        STRATEGY["opening_wheat"], STRATEGY["opening_melons"], ANIMAL_PLAN,
        STRATEGY["opening_carrots"],
    )
    CROP_PLAN = _build_crop_plan(STRATEGY["strawberries"], ANIMAL_PLAN)
    livestock_plan = _build_animal_plan(STRATEGY["livestock_cows"], STRATEGY["livestock_sheep"])
    premium_plan = _build_animal_plan(STRATEGY["premium_cows"], STRATEGY["premium_sheep"])
    ADAPTIVE_ANIMAL_PLANS = {
        None: ANIMAL_PLAN,
        "WHEAT_RUSH": ANIMAL_PLAN,
        "LIVESTOCK_RUSH": livestock_plan,
        "PREMIUM_CROP": premium_plan,
    }
    ADAPTIVE_CROP_PLANS = {
        None: CROP_PLAN,
        "WHEAT_RUSH": CROP_PLAN,
        "LIVESTOCK_RUSH": _build_crop_plan(
            STRATEGY["livestock_strawberries"], livestock_plan, STRATEGY["livestock_tomatoes"]
        ),
        "PREMIUM_CROP": _build_crop_plan(
            STRATEGY["premium_strawberries"], premium_plan, STRATEGY["premium_tomatoes"]
        ),
    }
    base_profile = {
        "hands": STRATEGY["hands"],
        "cows": STRATEGY["cows"],
        "sheep": STRATEGY["sheep"],
        "strawberries": STRATEGY["strawberries"],
        "tomatoes": 0,
        "cash_reserve": STRATEGY["cash_reserve"],
        "animal_cap": STRATEGY["animal_daily_cap"],
        "strawberry_last_plant": STRATEGY["strawberry_last_plant"],
    }
    EXPERT_PROFILES = {
        "BASE": base_profile,
        "WHEAT_RUSH": dict(
            base_profile,
            cash_reserve=STRATEGY["wheat_rush_cash_reserve"],
            animal_cap=STRATEGY["wheat_rush_animal_cap"],
        ),
        "COW_RUSH": dict(
            base_profile,
            cows=STRATEGY["cow_expert_cows"],
            sheep=STRATEGY["cow_expert_sheep"],
            cash_reserve=STRATEGY["livestock_cash_reserve"],
            animal_cap=STRATEGY["livestock_animal_cap"],
        ),
        "SHEEP_RUSH": dict(
            base_profile,
            cows=STRATEGY["sheep_expert_cows"],
            sheep=STRATEGY["sheep_expert_sheep"],
            cash_reserve=STRATEGY["livestock_cash_reserve"],
            animal_cap=STRATEGY["livestock_animal_cap"],
        ),
        "PREMIUM_CROP": dict(
            base_profile,
            cows=STRATEGY["premium_cows"],
            sheep=STRATEGY["premium_sheep"],
            strawberries=STRATEGY["premium_strawberries"],
            tomatoes=STRATEGY["premium_tomatoes"],
            cash_reserve=STRATEGY["premium_cash_reserve"],
            animal_cap=STRATEGY["premium_animal_cap"],
        ),
    }
    FIELD_PLAN = {pos: crop for pos, crop in OPENING_CROP_PLAN.items()}
    _OPPONENT_STYLE = None
    _EXPERT_EVIDENCE = {}
    _MARKET_ANIMAL_SHARE = None
    _V11_SELECTED_RADIANT_VARIANT = None
    _V13_MARKET_MODE = "BASE"
    _V13_MARKET_CONFIDENCE = 0.0
    _V13_MARKET_LOCK_UNTIL = -1
    _V14_MARKET_MODE = "BASE"
    _V14_MARKET_CONFIDENCE = 0.0
    _V14_MARKET_LOCK_UNTIL = -1
    _PLAN_CACHE = {}


def _expert_weights():
    forced = STRATEGY.get("force_expert")
    if forced in EXPERT_PROFILES:
        return {forced: 1.0}
    # Wheat-capital evidence represents an existential feed-price risk and
    # therefore owns the portfolio once confirmed.  Other regimes blend.
    if float(_EXPERT_EVIDENCE.get("WHEAT_RUSH", 0)) >= 0.8:
        return {"WHEAT_RUSH": 1.0}
    # Pure early sheep openings depress wool economics before a later herd is
    # visible.  Replay counterfactuals consistently favored keeping the base
    # 8/6 portfolio with extra liquidity, so this signal must act early.
    if float(_EXPERT_EVIDENCE.get("EARLY_SHEEP", 0)) >= 0.8:
        return {"PREMIUM_CROP": 1.0}
    evidence = {
        name: max(0.0, min(1.0, float(_EXPERT_EVIDENCE.get(name, 0))))
        for name in ("COW_RUSH", "SHEEP_RUSH", "PREMIUM_CROP")
    }
    # A farm that exposes both livestock regimes is rotating its market
    # pressure rather than specializing.  Chasing both sides produced the
    # weakest possible 7/7 herd in replay validation; the liquid balanced
    # expert is the robust response to this phase-changing portfolio.
    rotation_threshold = float(STRATEGY.get("rotation_evidence_threshold", 0.9))
    if evidence["COW_RUSH"] >= rotation_threshold and evidence["SHEEP_RUSH"] >= rotation_threshold:
        return {"PREMIUM_CROP": 1.0}
    active = sum(evidence.values())
    if active <= 0:
        return {"BASE": 1.0}
    # A clear signature selects the validated counter exactly.  Lower
    # confidence produces a genuine mixture with BASE, avoiding a brittle
    # all-or-nothing switch on borderline farms.
    expert_mass = 1.0 if max(evidence.values()) >= 0.9 else min(0.85, active)
    weights = {name: expert_mass * value / active for name, value in evidence.items() if value > 0}
    weights["BASE"] = 1.0 - expert_mass
    return weights


def _blended_targets():
    weights = _expert_weights()
    numeric = {}
    for key in ("hands", "cows", "sheep", "strawberries", "tomatoes", "cash_reserve", "animal_cap", "strawberry_last_plant"):
        numeric[key] = sum(weight * float(EXPERT_PROFILES[name][key]) for name, weight in weights.items())
    total_animals = max(0, round(numeric["cows"] + numeric["sheep"]))
    cows = min(total_animals, max(0, round(numeric["cows"])))
    if STRATEGY.get("price_adaptive_animals") and _MARKET_ANIMAL_SHARE is not None:
        cows = min(total_animals, max(0, round(total_animals * _MARKET_ANIMAL_SHARE)))
    return {
        "hands": max(0, round(numeric["hands"])),
        "cows": cows,
        "sheep": total_animals - cows,
        "strawberries": max(0, round(numeric["strawberries"])),
        "tomatoes": max(0, round(numeric["tomatoes"])),
        "cash_reserve": max(0, round(numeric["cash_reserve"])),
        "animal_cap": max(0, round(numeric["animal_cap"])),
        "strawberry_last_plant": max(0, round(numeric["strawberry_last_plant"])),
    }


def _crop_plan(day):
    if day < int(STRATEGY.get("crop_transition_day", 5)):
        return OPENING_CROP_PLAN
    targets = _blended_targets()
    strawberries = targets["strawberries"]
    if STRATEGY.get("strawberry_staging"):
        stages = ((3, 3), (4, 5), (5, 7), (7, 9), (9, 15), (10, 18), (11, 32), (12, 44))
        staged = strawberries
        for final_day, count in stages:
            if day <= final_day:
                staged = count
                break
        strawberries = min(strawberries, staged)
    animal_plan = _build_animal_plan(targets["cows"], targets["sheep"])
    key = (targets["cows"], targets["sheep"], strawberries, targets["tomatoes"])
    if key not in _PLAN_CACHE:
        _PLAN_CACHE[key] = _build_crop_plan(strawberries, animal_plan, targets["tomatoes"])
    return _PLAN_CACHE[key]


def _animal_plan():
    targets = _blended_targets()
    return _build_animal_plan(targets["cows"], targets["sheep"])


def _style_setting(base):
    """Return the soft-gated strategic target for a shared executor."""
    targets = _blended_targets()
    if base in targets:
        return targets[base]
    return STRATEGY[base]


configure_strategy()


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _copy_action(action):
    """Copy a scheduled action before an observation-dependent overlay."""
    if not isinstance(action, dict):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(order) for order in (action.get("hands") or [])],
        "market": [list(order) for order in (action.get("market") or [])],
    }


def _farm_pipeline(farm):
    """Estimate near-future market exposure from public farm assets.

    Opponent inventories are private, so this is deliberately a portfolio
    estimate rather than a prediction of the next exact action.  Yield already
    waiting on a tile receives extra weight, while recurring assets retain a
    smaller baseline weight even between production days.
    """
    exposure = {
        "WHEAT": 0.0,
        "CARROT": 0.0,
        "TOMATO": 0.0,
        "STRAWBERRY": 0.0,
        "MELON": 0.0,
        "EGG": 0.0,
        "MILK": 0.0,
        "WOOL": 0.0,
    }
    animals = 0
    unfed = 0
    for row in (_get(farm, "tiles", []) or []):
        for tile in row:
            if not isinstance(tile, dict):
                continue
            ready = max(0.0, float(tile.get("yield_units", 0) or 0))
            crop = tile.get("crop")
            if tile.get("kind") == "PLANT" and crop in exposure:
                # A live crop represents future supply; ready produce is much
                # more likely to collide with our sale in the next few turns.
                exposure[crop] += 1.0 + 2.0 * ready
            animal = tile.get("animal")
            product = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(animal)
            if product:
                animals += 1
                unfed += int(not bool(tile.get("fed_today", False)))
                cadence = {"EGG": 1.0, "MILK": 0.5, "WOOL": 1.0 / 3.0}[product]
                exposure[product] += cadence + 2.0 * ready
    # Feed demand is the only visible buy-side pressure worth considering.
    # Unfed animals increase urgency but do not prove that the shed is empty.
    exposure["WHEAT"] += animals + 0.5 * unfed
    exposure["ANIMALS"] = float(animals)
    exposure["UNFED"] = float(unfed)
    return exposure


def _opponent_pipeline(obs):
    farms = _get(obs, "farms", []) or []
    player = int(_get(obs, "player", 0))
    if len(farms) != 2 or player not in (0, 1):
        return {}
    return _farm_pipeline(farms[1 - player])


def _interference_value(obs, product, quantity=1, pipeline=None):
    """Relative denial value used only to sequence existing v8 sales."""
    pipeline = pipeline if pipeline is not None else _opponent_pipeline(obs)
    prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
    exposure = max(0.0, float(pipeline.get(product, 0.0)))
    price = max(1.0, float(prices.get(product, 1.0)))
    quantity = max(1.0, float(quantity or 1))
    # Exposure captures the opponent's likely supply; price captures how much
    # acceleration is denied if our sale reaches the shared market first.
    return exposure * price * min(quantity, 10.0)


def _safe_wheat_squeeze(obs, market_orders, pipeline):
    """Optionally add one strictly gated feed-denial order.

    This is disabled in the submitted defaults until it beats the unchanged
    v8 schedule out of sample.  Keeping the gate here makes that hypothesis
    directly testable without weakening the production executor.
    """
    if not STRATEGY.get("interference_wheat_squeeze") or len(market_orders) >= MAX_ORDERS:
        return market_orders
    day = int(_get(obs, "day", 0))
    hour = int(_get(obs, "hour", 0))
    if not (8 <= day <= 24 and hour == 0):
        return market_orders
    farms = _get(obs, "farms", []) or []
    player = int(_get(obs, "player", 0))
    if len(farms) != 2 or player not in (0, 1):
        return market_orders
    own = farms[player]
    opponent = farms[1 - player]
    if float(_get(own, "money", 0)) < float(STRATEGY.get("interference_wheat_min_cash", 10000)):
        return market_orders
    if float(pipeline.get("ANIMALS", 0)) < float(STRATEGY.get("interference_wheat_min_opponent_animals", 10)):
        return market_orders
    # Attack only a genuinely liquidity-sensitive herd, never a rich rival.
    if float(_get(opponent, "money", 0)) > 250:
        return market_orders
    prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
    if float(prices.get("WHEAT", 10 ** 9)) > float(STRATEGY.get("interference_wheat_price_cap", 30)):
        return market_orders
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    own_pipeline = _farm_pipeline(own)
    own_animals = int(own_pipeline.get("ANIMALS", 0))
    if int(shed.get("WHEAT", 0) or 0) < 2 * own_animals:
        return market_orders
    if any(order and order[0] == "SELL" and len(order) > 1 and order[1] == "WHEAT" for order in market_orders):
        return market_orders
    units = max(0, min(1, int(STRATEGY.get("interference_wheat_units", 1))))
    if units:
        market_orders.append(["BUY_PRODUCT", "WHEAT", units])
    return market_orders


def _apply_market_interference(obs, action):
    """Apply a market-only overlay without changing farm execution."""
    copied = _copy_action(action)
    if not STRATEGY.get("market_interference"):
        return copied
    pipeline = _opponent_pipeline(obs)
    if not pipeline:
        return copied
    orders = copied["market"]
    if STRATEGY.get("interference_sell_first"):
        targeted = bool(STRATEGY.get("interference_targeted_sort"))

        def priority(pair):
            index, order = pair
            is_sell = bool(order) and order[0] == "SELL"
            if not is_sell:
                return (1, 0.0, index)
            product = order[1] if len(order) > 1 else ""
            quantity = order[2] if len(order) > 2 else 1
            if STRATEGY.get("interference_preserve_wheat_order") and product == "WHEAT":
                return (1, 0.0, index)
            if (
                STRATEGY.get("interference_collision_only")
                and float(pipeline.get(product, 0.0))
                < float(STRATEGY.get("interference_min_exposure", 0.5))
            ):
                return (1, 0.0, index)
            value = _interference_value(obs, product, quantity, pipeline) if targeted else 0.0
            return (0, -value, index)

        orders = [order for _, order in sorted(enumerate(orders), key=priority)]
    copied["market"] = _safe_wheat_squeeze(obs, orders, pipeline)[:MAX_ORDERS]
    return copied


def _v13_market_mode(obs):
    """Select a market expert from public supply with daily hysteresis.

    Production and movement remain on one coherent route.  Only the ordering
    of already-planned sales may change, so a classification error cannot
    invalidate future farm actions.
    """
    global _V13_MARKET_MODE, _V13_MARKET_CONFIDENCE, _V13_MARKET_LOCK_UNTIL
    step = max(0, int(_get(obs, "step", 0)))
    hour = int(_get(obs, "hour", step % 24))
    if step == 0:
        _V13_MARKET_MODE = "BASE"
        _V13_MARKET_CONFIDENCE = 0.0
        _V13_MARKET_LOCK_UNTIL = -1
    if not STRATEGY.get("v13_market_adaptation", True):
        return "BASE"
    if step < _V13_MARKET_LOCK_UNTIL or (hour != 0 and step > 0):
        return _V13_MARKET_MODE

    pipeline = _opponent_pipeline(obs)
    values = [
        max(0.0, float(pipeline.get(product, 0.0)))
        for product in ("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL")
    ]
    total = sum(values)
    concentration = max(values, default=0.0) / total if total > 0 else 0.0
    scale = max(0.1, float(STRATEGY.get("v13_gate_exposure_scale", 6.0)))
    target_concentration = max(
        0.1, float(STRATEGY.get("v13_gate_concentration", 0.50))
    )
    confidence = min(1.0, total / scale) * min(
        1.0, concentration / target_concentration
    )
    _V13_MARKET_CONFIDENCE = confidence
    threshold = max(0.0, min(1.0, float(STRATEGY.get("v13_gate_confidence", 0.70))))
    next_mode = "COLLISION" if confidence >= threshold else "BASE"
    # Require substantially weaker contrary evidence before leaving an active
    # specialist.  Public assets normally change slowly, but this also covers
    # deliberate mid-game strategy reversals.
    if _V13_MARKET_MODE == "COLLISION" and confidence >= threshold * 0.5:
        next_mode = "COLLISION"
    if next_mode != _V13_MARKET_MODE:
        _V13_MARKET_MODE = next_mode
        _V13_MARKET_LOCK_UNTIL = step + max(
            1, int(STRATEGY.get("v13_gate_lock_steps", 24))
        )
    return _V13_MARKET_MODE


def _v13_senkin_action(obs, step):
    """Run the robust core plus a compatible opponent-conditioned expert."""
    copied = _copy_action(_V13_SENKIN_SCHEDULE[step])
    if _v13_market_mode(obs) != "COLLISION":
        return copied
    pipeline = _opponent_pipeline(obs)
    minimum = max(0.0, float(STRATEGY.get("v13_interference_min_exposure", 2.0)))

    def priority(pair):
        index, order = pair
        if not order or order[0] != "SELL" or len(order) < 2:
            return (1, 0.0, index)
        product = order[1]
        # Wheat is working capital for the coherent feed loop.  Its exact
        # buy/sell ordering is never changed by the market expert.
        if product == "WHEAT" or float(pipeline.get(product, 0.0)) < minimum:
            return (1, 0.0, index)
        quantity = order[2] if len(order) > 2 else 1
        return (0, -_interference_value(obs, product, quantity, pipeline), index)

    copied["market"] = [
        order for _, order in sorted(enumerate(copied["market"]), key=priority)
    ][:MAX_ORDERS]
    return copied


def _v14_market_mode(obs):
    """Select a collision expert using price-weighted public concentration.

    v13 measured concentration in physical exposure only.  v14 keeps the same
    conservative daily gate, but normalizes each visible product pipeline by
    its equilibrium price before measuring concentration.  This makes a
    premium product at the market floor weak evidence while preserving the
    signal from a genuinely valuable, concentrated pipeline.
    """
    global _V14_MARKET_MODE, _V14_MARKET_CONFIDENCE, _V14_MARKET_LOCK_UNTIL
    step = max(0, int(_get(obs, "step", 0)))
    hour = int(_get(obs, "hour", step % 24))
    if step == 0:
        _V14_MARKET_MODE = "BASE"
        _V14_MARKET_CONFIDENCE = 0.0
        _V14_MARKET_LOCK_UNTIL = -1
    if not STRATEGY.get("v14_market_adaptation", True):
        return "BASE"
    if step < _V14_MARKET_LOCK_UNTIL or (hour != 0 and step > 0):
        return _V14_MARKET_MODE

    pipeline = _opponent_pipeline(obs)
    products = ("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL")
    exposures = [max(0.0, float(pipeline.get(product, 0.0))) for product in products]
    total_exposure = sum(exposures)
    prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
    reference = {
        "CARROT": 35.0,
        "TOMATO": 60.0,
        "STRAWBERRY": 120.0,
        "MELON": 250.0,
        "EGG": 50.0,
        "MILK": 160.0,
        "WOOL": 200.0,
    }
    weighted = [
        exposure * max(1.0, float(prices.get(product, reference[product])))
        / reference[product]
        for product, exposure in zip(products, exposures)
    ]
    weighted_total = sum(weighted)
    concentration = max(weighted, default=0.0) / weighted_total if weighted_total > 0 else 0.0
    scale = max(0.1, float(STRATEGY.get("v14_gate_exposure_scale", 6.0)))
    target_concentration = max(0.1, float(STRATEGY.get("v14_gate_concentration", 0.50)))
    confidence = min(1.0, total_exposure / scale) * min(
        1.0, concentration / target_concentration
    )
    _V14_MARKET_CONFIDENCE = confidence
    threshold = max(0.0, min(1.0, float(STRATEGY.get("v14_gate_confidence", 0.70))))
    next_mode = "COLLISION" if confidence >= threshold else "BASE"
    if _V14_MARKET_MODE == "COLLISION" and confidence >= threshold * 0.5:
        next_mode = "COLLISION"
    if next_mode != _V14_MARKET_MODE:
        _V14_MARKET_MODE = next_mode
        _V14_MARKET_LOCK_UNTIL = step + max(
            1, int(STRATEGY.get("v14_gate_lock_steps", 24))
        )
    return _V14_MARKET_MODE


def _v14_senkin_action(obs, step):
    """Run the v13 route with v14's price-aware collision ordering."""
    copied = _copy_action(_V13_SENKIN_SCHEDULE[step])
    if _v14_market_mode(obs) != "COLLISION":
        return copied
    pipeline = _opponent_pipeline(obs)
    minimum = max(0.0, float(STRATEGY.get("v14_interference_min_exposure", 2.0)))

    def priority(pair):
        index, order = pair
        if not order or order[0] != "SELL" or len(order) < 2:
            return (1, 0.0, index)
        product = order[1]
        # WHEAT is the working-capital loop and remains in its validated order.
        if product == "WHEAT" or float(pipeline.get(product, 0.0)) < minimum:
            return (1, 0.0, index)
        quantity = order[2] if len(order) > 2 else 1
        return (0, -_interference_value(obs, product, quantity, pipeline), index)

    copied["market"] = [
        order for _, order in sorted(enumerate(copied["market"]), key=priority)
    ][:MAX_ORDERS]
    return copied


def _public_farm_counts(farm):
    """Return stable public portfolio features for a farm.

    Fixed replay executors cannot safely swap movement trajectories halfway
    through a game.  Animal species and within-turn purchase priority are
    different: both share the same pasture sites and unit actions, so they can
    react to public state without invalidating the remaining executor.
    """
    counts = {
        "COW": 0,
        "SHEEP": 0,
        "GOOSE": 0,
        "PLANTS": 0,
        "STRAWBERRY": 0,
        "LAND": len(_get(farm, "unlocked_quadrants", []) or []),
        "MONEY": float(_get(farm, "money", 0) or 0),
    }
    for row in (_get(farm, "tiles", []) or []):
        for tile in row:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal in ("COW", "SHEEP", "GOOSE"):
                counts[animal] += 1
            if tile.get("kind") == "PLANT":
                counts["PLANTS"] += 1
                if tile.get("crop") == "STRAWBERRY":
                    counts["STRAWBERRY"] += 1
    counts["ANIMALS"] = counts["COW"] + counts["SHEEP"] + counts["GOOSE"]
    return counts


def _adaptive_animal_focus(obs, own, opponent):
    """Choose a livestock market to contest from observable exposure only."""
    day = int(_get(obs, "day", 0))
    if not (
        int(STRATEGY.get("adaptive_animal_min_day", 2))
        <= day
        <= int(STRATEGY.get("adaptive_animal_max_day", 14))
    ):
        return None
    opponent_herd = opponent["COW"] + opponent["SHEEP"]
    if opponent_herd < int(STRATEGY.get("adaptive_animal_min_herd", 4)):
        return None
    lead = int(STRATEGY.get("adaptive_animal_lead", 2))
    if opponent["COW"] >= opponent["SHEEP"] + lead:
        focus = "COW"
    elif opponent["SHEEP"] >= opponent["COW"] + lead:
        focus = "SHEEP"
    elif STRATEGY.get("adaptive_tempo_cow") and (
        opponent["ANIMALS"] >= own["ANIMALS"] + int(
            STRATEGY.get("adaptive_tempo_animal_lead", 1)
        )
        or opponent["LAND"] >= own["LAND"] + int(
            STRATEGY.get("adaptive_tempo_land_lead", 1)
        )
    ):
        # Cows are the cheaper livestock asset and start the milk cycle sooner.
        # When a balanced rival is already ahead on capital, this is a recovery
        # branch rather than an attempt to infer a nonexistent specialization.
        focus = "COW"
    else:
        return None
    if STRATEGY.get("adaptive_animal_mode") == "diversify":
        focus = "SHEEP" if focus == "COW" else "COW"
    share = max(0.5, min(1.0, float(STRATEGY.get("adaptive_animal_target_share", 0.72))))
    own_herd = own["COW"] + own["SHEEP"]
    # Do not blindly convert every future purchase.  Stop contesting once the
    # requested share is already represented in our live herd.
    target = int(round((own_herd + 1) * share))
    return focus if own[focus] < target else None


def _prioritize_capital_orders(obs, orders, own, opponent):
    """Spend existing early orders sooner when the rival is accelerating.

    WHEAT orders keep their exact slots and relative order because the fixed
    executor uses them as a cash cycle.  Only non-WHEAT slots are permuted.
    """
    if not STRATEGY.get("adaptive_capital_priority"):
        return orders
    if int(_get(obs, "day", 0)) > int(STRATEGY.get("adaptive_capital_max_day", 12)):
        return orders
    animal_pressure = opponent["ANIMALS"] >= own["ANIMALS"] + int(
        STRATEGY.get("adaptive_capital_animal_lead", 2)
    )
    land_pressure = opponent["LAND"] >= own["LAND"] + int(
        STRATEGY.get("adaptive_capital_land_lead", 1)
    )
    if not (animal_pressure or land_pressure):
        return orders

    movable = []
    positions = []
    for index, order in enumerate(orders):
        if len(order) > 1 and order[1] == "WHEAT" and order[0] in {"BUY_PRODUCT", "SELL"}:
            continue
        positions.append(index)
        movable.append(order)

    def priority(pair):
        index, order = pair
        command = order[0] if order else ""
        if command == "SELL":
            return (0, index)
        if command in {"BUY_LAND", "BUY_ANIMAL"}:
            return (1, index)
        if command == "HIRE":
            return (2, index)
        return (3, index)

    reordered = list(orders)
    sorted_orders = [order for _, order in sorted(enumerate(movable), key=priority)]
    for index, order in zip(positions, sorted_orders):
        reordered[index] = order
    return reordered


def _apply_fixed_board_adaptation(obs, action):
    """Observation-only adaptation layered on a validated fixed executor."""
    copied = _copy_action(action)
    if not STRATEGY.get("fixed_board_adaptation"):
        return copied
    farms = _get(obs, "farms", []) or []
    player = int(_get(obs, "player", 0))
    if len(farms) != 2 or player not in (0, 1):
        return copied
    own = _public_farm_counts(farms[player])
    opponent = _public_farm_counts(farms[1 - player])
    focus = _adaptive_animal_focus(obs, own, opponent)
    if focus:
        for order in copied["market"]:
            if order and order[0] == "BUY_ANIMAL" and len(order) >= 2:
                order[1] = focus
    copied["market"] = _prioritize_capital_orders(obs, copied["market"], own, opponent)[:MAX_ORDERS]
    return copied


def _v11_radiant_schedule(obs, step):
    """Lock one coherent radiant trajectory from a public day-four price.

    The robust and alpha trajectories share actions 0..108 exactly.  Routing
    at step 109 therefore changes no prior farm state, and locking the choice
    prevents the invalid cross-trajectory oscillation seen in k-NN ablations.
    """
    global _V11_SELECTED_RADIANT_VARIANT
    variant = STRATEGY.get("v11_radiant_variant", "robust")
    if step == 0:
        _V11_SELECTED_RADIANT_VARIANT = None
    if variant in {"robust", "alpha"}:
        selected = variant
    else:
        route_step = int(STRATEGY.get("v11_route_step", 109))
        if step >= route_step and _V11_SELECTED_RADIANT_VARIANT is None:
            prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
            milk_price = float(prices.get("MILK", 0) or 0)
            _V11_SELECTED_RADIANT_VARIANT = (
                "alpha"
                if milk_price >= float(STRATEGY.get("v11_alpha_milk_price", 193))
                else "robust"
            )
        selected = _V11_SELECTED_RADIANT_VARIANT or "robust"
    return _V11_RADIANT_ALPHA_SCHEDULE if selected == "alpha" else _V11_RADIANT_SCHEDULE


def _v12_syouya_action(obs, step):
    """Apply only the two validated late gates to the coherent syouya route.

    Episodes 89511601 and 89512693 have identical movement and capital plans.
    Their first difference is the order of the terminal MILK/STRAWBERRY sales;
    public production capacity times the current price selects that order.
    """
    copied = _copy_action(_V12_SYOUYA_SCHEDULE[step])
    mode = STRATEGY.get("v12_late_market_mode", "price")
    if step == 624 and mode in {"asset", "price"}:
        farms = _get(obs, "farms", []) or []
        player = int(_get(obs, "player", 0))
        counts = (
            _public_farm_counts(farms[1 - player])
            if len(farms) == 2 and player in (0, 1)
            else {"COW": 0, "STRAWBERRY": 0}
        )
        if mode == "asset":
            milk_first = counts["COW"] >= counts["STRAWBERRY"]
        else:
            prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
            milk_value = counts["COW"] * float(prices.get("MILK", 0) or 0)
            strawberry_value = counts["STRAWBERRY"] * float(
                prices.get("STRAWBERRY", 0) or 0
            )
            milk_first = milk_value >= strawberry_value
        if not milk_first:
            priority = {
                "STRAWBERRY": 0,
                "MELON": 1,
                "FERTILIZER": 2,
                "MILK": 3,
                "WHEAT": 4,
            }
            sales = [order for order in copied["market"] if order and order[0] == "SELL"]
            other = [order for order in copied["market"] if not order or order[0] != "SELL"]
            copied["market"] = sorted(
                sales, key=lambda order: priority.get(order[1], len(priority))
            ) + other
    elif step == 714:
        shed = _get(_get(obs, "private", {}) or {}, "shed", {}) or {}
        if float(_get(shed, "FERTILIZER", 0) or 0) >= 2:
            copied["market"] = (copied["market"] + [["SELL", "FERTILIZER", 2]])[:MAX_ORDERS]
    return copied


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _shed_access(board_size):
    half = board_size // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _available_access(tiles):
    """Shed corners that belong to currently unlocked quadrants."""
    access = _shed_access(len(tiles) or 10)
    available = tuple(p for p in access if tiles[p[1]][p[0]] != "LOCKED") if tiles else ()
    return available or (access[0],)


def _move_toward(pos, target, tiles=None):
    """Return a shortest move while avoiding still-locked quadrants."""
    x, y = pos
    tx, ty = target
    if tiles:
        moves = (("NORTH", 0, -1), ("WEST", -1, 0), ("EAST", 1, 0), ("SOUTH", 0, 1))
        queue = [(x, y, None)]
        seen = {(x, y)}
        for cx, cy, first in queue:
            if (cx, cy) == (tx, ty):
                return [first] if first else ["PASS"]
            for name, dx, dy in moves:
                nx, ny = cx + dx, cy + dy
                if not (0 <= ny < len(tiles) and 0 <= nx < len(tiles[ny])) or (nx, ny) in seen:
                    continue
                if tiles[ny][nx] == "LOCKED":
                    continue
                seen.add((nx, ny))
                queue.append((nx, ny, first or name))
        return ["PASS"]
    if abs(tx - x) >= abs(ty - y) and x != tx:
        return ["EAST" if x < tx else "WEST"]
    if y != ty:
        return ["SOUTH" if y < ty else "NORTH"]
    if x != tx:
        return ["EAST" if x < tx else "WEST"]
    return ["PASS"]


def _count_inventory(inv):
    if not isinstance(inv, dict):
        return 0
    return sum(max(0, int(v)) for v in inv.values())


def _asset_counts(obs):
    player = int(_get(obs, "player", 0))
    farm = _get(obs, "farms", [])[player]
    private = _get(obs, "private", {}) or {}
    counts = {name: 0 for name in ANIMALS}
    for row in _get(farm, "tiles", []):
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal") in counts:
                counts[tile["animal"]] += 1
    shed = _get(private, "shed", {}) or {}
    inventories = _get(private, "inventories", []) or []
    for animal in counts:
        counts[animal] += int(shed.get(animal, 0))
        counts[animal] += sum(int(inv.get(animal, 0)) for inv in inventories if isinstance(inv, dict))
    return counts


def _active_target(pos, day, unlocked):
    x, y = pos
    if x < 5 and y < 5:
        return True
    if x >= 5 and y < 5:
        return "NE" in unlocked and day >= 7
    if x < 5 and y >= 5:
        return "SW" in unlocked and day >= 9
    return False


def _animal_site_active(pos, day, unlocked):
    """Stage livestock growth so labour and feed can grow before the herd."""
    try:
        index = ANIMAL_SITES.index(pos)
    except ValueError:
        return False
    opening_animals = min(4, max(0, int(STRATEGY.get("opening_animals", 2))))
    if index < opening_animals:
        return True
    if index < 4:
        return day >= int(STRATEGY.get("animal_nw_day", 4))
    if index < 9:
        return day >= int(STRATEGY.get("animal_ne_day", 8)) and "NE" in unlocked
    return day >= int(STRATEGY.get("animal_sw_day", 12)) and "SW" in unlocked


def _crop_is_ripe(tile, day, hour):
    crop = tile.get("crop")
    spec = CROPS.get(crop)
    if not spec or int(tile.get("yield_units", 0)) <= 0:
        return False
    age = day - int(tile.get("planted_day", day))
    if age < spec["first"]:
        return False
    if not spec["ongoing"]:
        return int(tile.get("yield_units", 0)) >= spec["max_yield"] or age >= spec["max_day"]
    # Avoid hitting the held-yield cap, and cash out anything available near
    # the end of the season.
    threshold = max(1, int(STRATEGY.get("ongoing_harvest_threshold", 3)))
    return (
        int(tile.get("yield_units", 0)) >= threshold
        or day >= 28
        or (hour >= 18 and int(tile.get("yield_units", 0)) >= min(2, threshold))
    )


def _last_plant(crop):
    if crop == "STRAWBERRY":
        return int(_style_setting("strawberry_last_plant"))
    return int(CROPS[crop]["last_plant"])


def _fertilizer_value(tile, day, prices):
    """Expected value of one 3-day fertilizer application on a strawberry."""
    roi = STRATEGY.get("fertilizer_roi")
    if roi is None or tile.get("crop") != "STRAWBERRY":
        return 0
    if int(tile.get("fertilized_until_day", -1)) >= day + 1:
        return 0
    planted = int(tile.get("planted_day", day))
    bonus_ticks = 0
    for current_day in range(day, day + 3):
        since_first = current_day + 1 - planted - CROPS["STRAWBERRY"]["first"]
        if since_first >= 0 and since_first % 2 == 0 and since_first // 2 < CROPS["STRAWBERRY"]["max_yield"]:
            bonus_ticks += 1
    value = bonus_ticks * float(prices.get("STRAWBERRY", 120))
    cost = float(prices.get("FERTILIZER", 100)) * float(roi)
    return bonus_ticks if bonus_ticks and value >= cost else 0


def _fertilizer_positions(obs):
    player = int(_get(obs, "player", 0))
    farm = _get(obs, "farms", [])[player]
    day = int(_get(obs, "day", 0))
    prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
    positions = []
    for y, row in enumerate(_get(farm, "tiles", [])):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and _fertilizer_value(tile, day, prices):
                positions.append((x, y))
    return positions


def _task(priority, pos, action, requirement=None, tag=""):
    return (priority, pos, action, requirement, tag)


def _build_tasks(obs, positions, inventories):
    player = int(_get(obs, "player", 0))
    farm = _get(obs, "farms", [])[player]
    tiles = _get(farm, "tiles", [])
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    seeds = _get(private, "seeds", {}) or {}
    day = int(_get(obs, "day", 0))
    hour = int(_get(obs, "hour", 0))
    unlocked = set(_get(farm, "unlocked_quadrants", ["NW"]) or ["NW"])
    access = _available_access(tiles)
    tasks = []
    crop_plan = _crop_plan(day)
    animal_plan = _animal_plan()
    fertilizer_positions = set(_fertilizer_positions(obs))

    animals = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict):
                continue
            if tile.get("animal") in ANIMALS:
                animals.append(((x, y), tile))
                if day < 29 and not tile.get("fed_today", False):
                    urgent = 0 if int(tile.get("consecutive_unfed", 0)) >= 1 or hour >= 15 else 2
                    tasks.append(_task(urgent, (x, y), ["FEED"], "WHEAT", "feed"))
                if int(tile.get("yield_units", 0)) > 0:
                    tasks.append(_task(1, (x, y), ["HARVEST"], None, "harvest"))
                if not tile.get("cared_today", False) and day < 29:
                    tasks.append(_task(3, (x, y), ["CARE"], None, "care"))
                if tile.get("fertilizer_available", False):
                    tasks.append(_task(4, (x, y), ["COLLECT_FERTILIZER"], None, "fertilizer"))

    # Crop preservation and harvest precede new construction.
    for (x, y), desired in crop_plan.items():
        if y >= len(tiles) or x >= len(tiles[y]) or not _active_target((x, y), day, unlocked):
            continue
        tile = tiles[y][x]
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            if _crop_is_ripe(tile, day, hour):
                tasks.append(_task(1, (x, y), ["HARVEST"], None, "harvest"))
            elif not tile.get("watered_today", False):
                crop = tile.get("crop")
                age = day - int(tile.get("planted_day", day))
                spec = CROPS.get(crop, CROPS["WHEAT"])
                in_bonus = not spec["ongoing"] and (spec["max_day"] + 1) // 2 <= age <= spec["max_day"]
                urgent = int(tile.get("consecutive_unwatered", 0)) >= 1 or hour >= 16
                # Ongoing crops need only alternate-day watering; one-time crop
                # bonus windows are watered every day.
                needs_fertilizer_water = (x, y) in fertilizer_positions or int(tile.get("fertilized_until_day", -1)) >= day
                if urgent or in_bonus or needs_fertilizer_water:
                    tasks.append(_task(0 if urgent else 2 if needs_fertilizer_water else 3, (x, y), ["WATER"], None, "water"))
            if (x, y) in fertilizer_positions:
                tasks.append(_task(2, (x, y), ["FERTILIZE"], "FERTILIZER", "fertilize"))

    # Build and populate livestock sites before filling expansion crops.
    for pos, animal in animal_plan.items():
        x, y = pos
        if y >= len(tiles) or x >= len(tiles[y]) or not _animal_site_active(pos, day, unlocked):
            continue
        tile = tiles[y][x]
        if tile is None:
            tasks.append(_task(5, pos, ["BUILD_PASTURE"], None, "build"))
        elif isinstance(tile, dict) and tile.get("kind") == "PASTURE" and "animal" not in tile:
            tasks.append(_task(1, pos, ["PLACE", animal], animal, "place"))
        elif isinstance(tile, dict) and tile.get("kind") in ("WEED", "PLANT"):
            tasks.append(_task(5, pos, ["DIG"], None, "dig"))

    # Land preparation and planting.  Seed demand is capped here so atomic
    # validation cannot cancel several simultaneous PLANT actions.
    remaining = {crop: int(seeds.get(crop, 0)) for crop in CROPS}
    for pos, crop in crop_plan.items():
        x, y = pos
        if y >= len(tiles) or x >= len(tiles[y]) or not _active_target(pos, day, unlocked):
            continue
        tile = tiles[y][x]
        if isinstance(tile, dict) and tile.get("kind") == "WEED":
            if day <= _last_plant(crop):
                tasks.append(_task(6, pos, ["DIG"], None, "dig"))
        elif tile is None and day <= _last_plant(crop) and remaining[crop] > 0:
            tasks.append(_task(7, pos, ["PLANT", crop], None, "plant"))
            remaining[crop] -= 1

    # Operational inventory pickups.  A few loaded units can visit several
    # animals, which is much cheaper than sending every hand back to the shed.
    unfed = sum(not tile.get("fed_today", False) for _, tile in animals)
    carried_wheat = sum(int(inv.get("WHEAT", 0)) for inv in inventories if isinstance(inv, dict))
    if unfed > carried_wheat and int(shed.get("WHEAT", 0)) > 0:
        carriers = min(3, max(1, (unfed - carried_wheat + 3) // 4))
        quantity = min(int(shed.get("WHEAT", 0)), max(1, (unfed - carried_wheat + carriers - 1) // carriers))
        for i in range(carriers):
            tasks.append(_task(1, access[i % len(access)], ["PICKUP", "WHEAT", quantity], None, "pickup_wheat"))

    carried_fertilizer = sum(int(inv.get("FERTILIZER", 0)) for inv in inventories if isinstance(inv, dict))
    fertilizer_deficit = len(fertilizer_positions) - carried_fertilizer
    if fertilizer_deficit > 0 and int(shed.get("FERTILIZER", 0)) > 0:
        carriers = min(3, max(1, (fertilizer_deficit + 3) // 4))
        quantity = min(int(shed.get("FERTILIZER", 0)), max(1, (fertilizer_deficit + carriers - 1) // carriers))
        for i in range(carriers):
            tasks.append(_task(1, access[-(i % len(access)) - 1], ["PICKUP", "FERTILIZER", quantity], None, "pickup_fertilizer"))

    for animal in ANIMALS:
        empty_positions = [
            pos for pos, target in animal_plan.items()
            if target == animal and _active_target(pos, day, unlocked)
            and isinstance(tiles[pos[1]][pos[0]], dict)
            and tiles[pos[1]][pos[0]].get("kind") == "PASTURE"
            and "animal" not in tiles[pos[1]][pos[0]]
        ]
        empty = len(empty_positions)
        carried = sum(int(inv.get(animal, 0)) for inv in inventories if isinstance(inv, dict))
        if empty > carried and int(shed.get(animal, 0)) > 0:
            pickup = min(access, key=lambda a: (min(_distance(a, target) for target in empty_positions), a[1], a[0]))
            tasks.append(_task(1, pickup, ["PICKUP", animal, min(empty - carried, int(shed.get(animal, 0)))], None, "pickup_animal"))

    return tasks


def _eligible(task, inv):
    requirement = task[3]
    return requirement is None or (isinstance(inv, dict) and int(inv.get(requirement, 0)) > 0)


def _quadrant(pos):
    x, y = pos
    return "NW" if x < 5 and y < 5 else "NE" if y < 5 else "SW" if x < 5 else "SE"


def _worker_zone(index, unlocked):
    if "SW" in unlocked:
        return "NW" if index < 4 else "NE" if index < 9 else "SW"
    if "NE" in unlocked:
        return "NW" if index < 4 else "NE"
    return "NW"


def _assign_actions(obs):
    player = int(_get(obs, "player", 0))
    farm = _get(obs, "farms", [])[player]
    private = _get(obs, "private", {}) or {}
    positions = [tuple(_get(farm, "farmer", (4, 4)))] + [tuple(p) for p in (_get(farm, "hands", []) or [])]
    inventories = list(_get(private, "inventories", []) or [])
    while len(inventories) < len(positions):
        inventories.append({})
    day = int(_get(obs, "day", 0))
    hour = int(_get(obs, "hour", 0))
    access = _available_access(_get(farm, "tiles", []))
    tasks = _build_tasks(obs, positions, inventories)
    actions = [["PASS"] for _ in positions]
    free = set(range(len(positions)))

    # Purchased livestock is high-value, per-unit inventory.  Route carriers
    # directly instead of letting generic nearby tasks repeatedly steal them.
    tiles = _get(farm, "tiles", [])
    unlocked = set(_get(farm, "unlocked_quadrants", ["NW"]) or ["NW"])
    animal_plan = _animal_plan()
    reserved_targets = set()

    # Feeding is an existential task: two unfed days delete the animal.  Keep
    # designated carriers moving to the shed instead of allowing generic
    # nearest-task matching to redirect them to watering on every turn.
    if day < 29:
        unfed = [
            (x, y)
            for y, row in enumerate(tiles)
            for x, tile in enumerate(row)
            if isinstance(tile, dict)
            and tile.get("animal") in ANIMALS
            and not tile.get("fed_today", False)
        ]
        carried_wheat = sum(int(inv.get("WHEAT", 0)) for inv in inventories if isinstance(inv, dict))
        shed = _get(private, "shed", {}) or {}
        deficit = max(0, len(unfed) - carried_wheat)
        if deficit and int(shed.get("WHEAT", 0)) > 0:
            carriers = min(3, max(1, (deficit + 3) // 4), len(free))
            candidates = [
                idx for idx in free
                if isinstance(inventories[idx], dict)
                and not any(int(inventories[idx].get(a, 0)) > 0 for a in ANIMALS)
                and int(inventories[idx].get("WHEAT", 0)) == 0
            ]
            candidates.sort(key=lambda idx: min(_distance(positions[idx], p) for p in access))
            remaining_wheat = min(deficit, int(shed.get("WHEAT", 0)))
            for number, idx in enumerate(candidates[:carriers]):
                remaining_carriers = carriers - number
                quantity = max(1, (remaining_wheat + remaining_carriers - 1) // remaining_carriers)
                target = min(access, key=lambda p: (_distance(positions[idx], p), p[1], p[0]))
                actions[idx] = ["PICKUP", "WHEAT", quantity] if positions[idx] in access else _move_toward(positions[idx], target, tiles)
                remaining_wheat = max(0, remaining_wheat - quantity)
                free.discard(idx)

    for idx, (pos, inv) in enumerate(zip(positions, inventories)):
        if idx not in free:
            continue
        if not isinstance(inv, dict):
            continue
        animal = next((name for name in ANIMALS if int(inv.get(name, 0)) > 0), None)
        if animal is None:
            continue
        targets = [
            target
            for target, desired in animal_plan.items()
            if desired == animal
            and target not in reserved_targets
            and _active_target(target, day, unlocked)
            and isinstance(tiles[target[1]][target[0]], dict)
            and tiles[target[1]][target[0]].get("kind") == "PASTURE"
            and "animal" not in tiles[target[1]][target[0]]
        ]
        if not targets:
            continue
        target = min(targets, key=lambda p: (_distance(pos, p), p[1], p[0]))
        reserved_targets.add(target)
        actions[idx] = ["PLACE", animal] if pos == target else _move_toward(pos, target, tiles)
        free.discard(idx)

    # Late-day liquidation is explicit.  On other turns inventories stay on
    # workers and auto-drop overnight, saving hundreds of return-path moves.
    for idx, (pos, inv) in enumerate(zip(positions, inventories)):
        if idx not in free:
            continue
        n = _count_inventory(inv)
        if n == 0:
            continue
        operational = sum(int(inv.get(k, 0)) for k in ("WHEAT", "FERTILIZER", "COW", "SHEEP")) if isinstance(inv, dict) else 0
        harvest_load = n - operational
        load_threshold = max(1, int(STRATEGY.get("drop_load_threshold", 30)))
        should_drop = (
            (day >= 29 and hour >= 12)
            or (hour >= 21 and harvest_load > 0)
            or harvest_load >= load_threshold
        )
        if should_drop:
            target = min(access, key=lambda p: (_distance(pos, p), p[1], p[0]))
            actions[idx] = ["DROP"] if pos in access else _move_toward(pos, target, tiles)
            free.discard(idx)

    # Minimum-distance matching within each priority band.  The slight tag
    # penalty keeps loaded feed/animal carriers focused on compatible work.
    for priority in sorted({t[0] for t in tasks}):
        pending = [t for t in tasks if t[0] == priority]
        while pending and free:
            candidates = []
            for unit in free:
                inv = inventories[unit]
                for j, task in enumerate(pending):
                    if not _eligible(task, inv):
                        continue
                    dist = _distance(positions[unit], task[1])
                    # Never distract a unit carrying a purchased animal with a
                    # generic nearby job; placement unlocks its daily revenue.
                    carried_animal = any(int(inv.get(a, 0)) > 0 for a in ANIMALS) if isinstance(inv, dict) else False
                    if carried_animal and task[4] != "place":
                        dist += 100
                    if STRATEGY.get("zoned_workers") and task[4] not in ("pickup_wheat", "pickup_fertilizer", "pickup_animal"):
                        if _quadrant(task[1]) != _worker_zone(unit, unlocked):
                            dist += 20
                    candidates.append((dist, unit, task[1][1], task[1][0], j))
            if not candidates:
                break
            _, unit, _, _, task_idx = min(candidates)
            task = pending.pop(task_idx)
            actions[unit] = task[2] if positions[unit] == task[1] else _move_toward(positions[unit], task[1], tiles)
            free.remove(unit)

    return actions


def _quadrant_crop_deficits(obs):
    player = int(_get(obs, "player", 0))
    farm = _get(obs, "farms", [])[player]
    private = _get(obs, "private", {}) or {}
    tiles = _get(farm, "tiles", [])
    seeds = _get(private, "seeds", {}) or {}
    day = int(_get(obs, "day", 0))
    unlocked = set(_get(farm, "unlocked_quadrants", ["NW"]) or ["NW"])
    deficits = {crop: 0 for crop in CROPS}
    for pos, crop in _crop_plan(day).items():
        x, y = pos
        if not _active_target(pos, day, unlocked) or day > _last_plant(crop):
            continue
        tile = tiles[y][x]
        if tile is None or (isinstance(tile, dict) and tile.get("kind") == "WEED"):
            deficits[crop] += 1
    for crop in deficits:
        deficits[crop] = max(0, deficits[crop] - int(seeds.get(crop, 0)))
    return deficits


def _hire_target(day):
    target = int(_style_setting("hands"))
    if STRATEGY.get("top_hire_ramp"):
        if day == 0:
            return min(4, target)
        if day <= 3:
            return min(5, target)
        if day <= 6:
            return min(6, target)
        if day <= 8:
            return min(7, target)
        if day == 9:
            return min(9, target)
        if day == 10:
            return min(10, target)
        if day <= 28:
            return target
        return min(6, target)
    if day == 0:
        return min(7, target)
    if day == 1:
        return min(4, target)
    if day == 2:
        return min(7, target)
    if day <= 4:
        return min(8, target)
    if day <= 28:
        return target
    # Final-day labour pays for itself by harvesting and liquidating the last
    # livestock output; one farmer cannot clear a mature fourteen-animal farm.
    return min(6, target)


def _hire_costs(target, already):
    fib_a, fib_b = 1, 1
    costs = []
    for index in range(max(0, int(target))):
        if index >= max(0, int(already)):
            costs.append(fib_a)
        fib_a, fib_b = fib_b, fib_a + fib_b
    return costs


def _safe_buy_price(price):
    """Budget for simultaneous opponent orders moving a market price."""
    price = max(1, int(price))
    pct = max(0, int(STRATEGY.get("price_buffer_pct", 10)))
    return max(price + 2, (price * (100 + pct) + 99) // 100)


def _observe_opponent(obs):
    """Accumulate public evidence and softly gate strategic experts.

    The features deliberately describe economic exposure rather than an
    opponent identity.  Thus an unseen agent with the same public portfolio
    receives the same response, while ambiguous portfolios remain blended
    with the broadly robust base strategy.
    """
    global _OPPONENT_STYLE, _EXPERT_EVIDENCE, _MARKET_ANIMAL_SHARE
    day = int(_get(obs, "day", 0))
    hour = int(_get(obs, "hour", 0))
    if day == 0 and hour == 0:
        _OPPONENT_STYLE = None
        _EXPERT_EVIDENCE = {}
        _MARKET_ANIMAL_SHARE = None
    market = _get(obs, "market", {}) or {}
    prices = _get(market, "prices", {}) or {}
    cow_roi = max(1.0, float(prices.get("MILK", 160))) / float(ANIMALS["COW"]["cost"])
    sheep_roi = max(1.0, float(prices.get("WOOL", 200))) / float(ANIMALS["SHEEP"]["cost"])
    sensitivity = max(0.1, float(STRATEGY.get("animal_price_sensitivity", 2.0)))
    cow_weight = cow_roi ** sensitivity
    sheep_weight = sheep_roi ** sensitivity
    _MARKET_ANIMAL_SHARE = cow_weight / (cow_weight + sheep_weight)
    farms = _get(obs, "farms", []) or []
    player = int(_get(obs, "player", 0))
    if day > 12 or len(farms) < 2:
        return
    opponent = farms[1 - player]
    tiles = [tile for row in (_get(opponent, "tiles", []) or []) for tile in row if isinstance(tile, dict)]
    plants = sum(tile.get("kind") == "PLANT" for tile in tiles)
    wheat = sum(tile.get("crop") == "WHEAT" for tile in tiles)
    strawberries = sum(tile.get("crop") == "STRAWBERRY" for tile in tiles)
    cows = sum(tile.get("animal") == "COW" for tile in tiles)
    sheep = sum(tile.get("animal") == "SHEEP" for tile in tiles)
    animals = sum(tile.get("animal") in ANIMALS for tile in tiles)
    land = len(_get(opponent, "unlocked_quadrants", []) or [])

    evidence = {}
    if day <= 3 and sheep >= 2 and cows == 0:
        evidence["EARLY_SHEEP"] = 1.0
    # Hak-like capital engine: a second quadrant full of wheat precedes a
    # large cattle wave.  Detecting it before day four prevents feed-price
    # contention from deleting our opening herd.
    if day <= 4 and land >= 2 and plants >= 28 and wheat >= 20 and animals <= 1:
        evidence["WHEAT_RUSH"] = 1.0

    # Livestock evidence is split by the opponent's exposed market demand.
    # Extreme sheep portfolios get their own counter; mixed portfolios use
    # the cow-heavy response already validated in v5.
    clear_livestock = (day <= 6 and animals >= 5 and plants <= 5) or (
        7 <= day <= 12 and animals >= 8 and plants <= 20 and strawberries <= 2
    )
    partial_livestock = 5 <= day <= 12 and animals >= 4 and plants <= 12 and strawberries <= 2
    if clear_livestock or partial_livestock:
        name = "SHEEP_RUSH" if sheep >= 5 and sheep >= 3 * max(1, cows) else "COW_RUSH"
        evidence[name] = 0.95 if clear_livestock else min(0.75, 0.35 + 0.08 * (animals - 4))

    # Repeated high-value crops imply a liquidity-sensitive strategy.  Once a
    # clear livestock regime is established we retain that earlier structural
    # signal: a late strawberry patch should not erase the proven counter.
    livestock_locked = max(
        float(_EXPERT_EVIDENCE.get("COW_RUSH", 0)),
        float(_EXPERT_EVIDENCE.get("SHEEP_RUSH", 0)),
        float(evidence.get("COW_RUSH", 0)),
        float(evidence.get("SHEEP_RUSH", 0)),
    ) >= 0.9
    if not livestock_locked:
        if (day >= 7 and strawberries >= 16) or (
            day >= 10 and strawberries >= 12 and plants >= 25
        ):
            evidence["PREMIUM_CROP"] = 1.0
        elif day >= 7 and strawberries >= 8:
            evidence["PREMIUM_CROP"] = min(0.75, 0.25 + strawberries / 40)

    for name, confidence in evidence.items():
        _EXPERT_EVIDENCE[name] = max(float(_EXPERT_EVIDENCE.get(name, 0)), confidence)
    if _EXPERT_EVIDENCE:
        _OPPONENT_STYLE = max(
            _EXPERT_EVIDENCE,
            key=lambda name: (_EXPERT_EVIDENCE[name], name == "WHEAT_RUSH", name),
        )


def _animal_purchase_cap():
    return max(0, int(_style_setting("animal_cap")))


def _market_orders(obs):
    player = int(_get(obs, "player", 0))
    farm = _get(obs, "farms", [])[player]
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    inventories = _get(private, "inventories", []) or []
    market = _get(obs, "market", {}) or {}
    prices = _get(market, "prices", {}) or {}
    day = int(_get(obs, "day", 0))
    unlocked = list(_get(farm, "unlocked_quadrants", ["NW"]) or ["NW"])
    orders = []
    budget = float(_get(farm, "money", 0))

    # Cash conversion first funds all later orders in the same turn.
    fertilizer = int(shed.get("FERTILIZER", 0))
    fertilizer_reserve = 0
    if STRATEGY.get("fertilizer_roi") is not None and day < 29:
        fertilizer_reserve = min(fertilizer, len(_fertilizer_positions(obs)) + 3)
    fertilizer_sale = max(0, fertilizer - fertilizer_reserve)
    if fertilizer_sale > 0:
        orders.append(["SELL", "FERTILIZER", fertilizer_sale])
        budget += fertilizer_sale * float(prices.get("FERTILIZER", 1)) * 0.95
    for item in SELLABLE:
        quantity = int(shed.get(item, 0))
        if quantity > 0:
            orders.append(["SELL", item, quantity])
            budget += quantity * float(prices.get(item, 1)) * 0.95
    # Wheat is working capital for feed.  Sell only a large surplus or all of
    # it on the final day.
    counts = _asset_counts(obs)
    animal_count = sum(counts.values())
    wheat_total = int(shed.get("WHEAT", 0)) + sum(int(inv.get("WHEAT", 0)) for inv in inventories if isinstance(inv, dict))
    wheat_reserve = 0 if day >= 29 else animal_count + 3
    wheat_sale = max(0, int(shed.get("WHEAT", 0)) - wheat_reserve)
    if wheat_sale > 0:
        orders.append(["SELL", "WHEAT", wheat_sale])
        budget += wheat_sale * float(prices.get("WHEAT", 1)) * 0.95

    target_counts = {animal: 0 for animal in ANIMALS}
    unlocked_set = set(unlocked)
    for pos, animal in _animal_plan().items():
        if _animal_site_active(pos, day, unlocked_set):
            target_counts[animal] += 1

    # Maintenance comes before growth.  Secure a small critical crew first,
    # then feed, then finish the desired crew.  This ordering survives order
    # caps and prevents land/livestock purchases from consuming tomorrow's
    # operating cash.
    target_hires = _hire_target(day)
    already = int(_get(farm, "hires_today", 0))
    hire_costs = _hire_costs(target_hires, already)
    critical_target = min(target_hires, 5 if day == 0 else 2 if day <= 4 else 4)
    critical_costs = _hire_costs(critical_target, already)
    hired_costs = 0
    for cost in critical_costs:
        if len(orders) >= MAX_ORDERS or budget < cost:
            break
        orders.append(["HIRE"])
        budget -= cost
        hired_costs += 1

    # Keep one full feeding plus a small buffer.  Use a buffered unit price so
    # a simultaneous opponent purchase cannot invalidate the last hire.
    feed_days = max(1, int(STRATEGY.get("feed_days_buffer", 1)))
    desired_wheat = 0 if day >= 29 else animal_count * feed_days + 2
    feed_deficit = max(0, desired_wheat - wheat_total)
    wheat_price = _safe_buy_price(prices.get("WHEAT", 25))
    buy_feed = min(feed_deficit, int(budget // wheat_price))
    if buy_feed > 0 and len(orders) < MAX_ORDERS:
        orders.append(["BUY_PRODUCT", "WHEAT", buy_feed])
        budget -= buy_feed * wheat_price

    liquidity_floor = 0 if day >= 15 else int(STRATEGY.get("early_liquidity_floor", 0))
    for cost in hire_costs[hired_costs:]:
        if len(orders) >= MAX_ORDERS or budget - cost < liquidity_floor:
            break
        orders.append(["HIRE"])
        budget -= cost

    deficits = _quadrant_crop_deficits(obs)
    # Stage the initial plan exactly; expansion fills premium crops only while
    # their observed price still covers the remaining-yield break-even point.
    activation = {
        "MELON": 0,
        "CARROT": 0,
        "WHEAT": 0,
        "STRAWBERRY": int(STRATEGY.get("strawberry_activation_day", 4)),
        "TOMATO": 8,
    }
    operating_reserve = max(int(_style_setting("cash_reserve")), (animal_count * feed_days + 2) * wheat_price)
    for crop in ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO"):
        if day < activation[crop] or len(orders) >= MAX_ORDERS:
            continue
        if crop == "STRAWBERRY" and float(prices.get(crop, 120)) < 35:
            continue
        if crop == "MELON" and day > 10 and float(prices.get(crop, 250)) < 35:
            continue
        needed = deficits[crop]
        affordable = int(max(0, budget - operating_reserve) // CROPS[crop]["seed"])
        quantity = min(needed, affordable)
        if crop == "MELON" and day == 0 and STRATEGY.get("opening_melon_day0_cap") is not None:
            quantity = min(quantity, max(0, int(STRATEGY["opening_melon_day0_cap"])))
        elif crop == "MELON" and day <= 3 and STRATEGY.get("opening_melon_early_cap") is not None:
            quantity = min(quantity, max(0, int(STRATEGY["opening_melon_early_cap"])))
        if quantity > 0 and len(orders) < MAX_ORDERS:
            orders.append(["BUY_SEED", crop, quantity])
            budget -= quantity * CROPS[crop]["seed"]

    # Expand only with capital left after labour, feed, crops, and a cash
    # reserve.  At most two animals are added per day to avoid workload shocks.
    land_cost = 0
    if day >= int(STRATEGY.get("land_ne_day", 5)) and "NE" not in unlocked and budget - operating_reserve >= 1000:
        land_cost = 1000
    elif (
        day >= int(STRATEGY.get("land_sw_day", 10))
        and "NE" in unlocked
        and "SW" not in unlocked
        and budget - operating_reserve >= 2000
    ):
        land_cost = 2000
    if land_cost and len(orders) < MAX_ORDERS:
        orders.append(["BUY_LAND"])
        budget -= land_cost

    remaining_animal_slots = _animal_purchase_cap()
    for animal in ("COW", "SHEEP"):
        needed = max(0, target_counts[animal] - counts[animal])
        capital_per_animal = ANIMALS[animal]["cost"] + 2 * wheat_price
        affordable = int(max(0, budget - operating_reserve) // capital_per_animal)
        quantity = min(needed, affordable, remaining_animal_slots)
        if quantity > 0 and len(orders) < MAX_ORDERS:
            orders.append(["BUY_ANIMAL", animal, quantity])
            budget -= quantity * capital_per_animal
            remaining_animal_slots -= quantity

    return orders[:MAX_ORDERS]


def agent(obs):
    """Kaggle entry point."""
    try:
        if STRATEGY.get("use_fixed_schedule"):
            version = STRATEGY.get("fixed_schedule_version")
            player = int(_get(obs, "player", 0))
            use_radiant = version == "v11" and player == int(
                STRATEGY.get("v11_radiant_player", 0)
            )
            if use_radiant:
                step = min(max(0, int(_get(obs, "step", 0))), len(_V11_RADIANT_SCHEDULE) - 1)
                schedule = _v11_radiant_schedule(obs, step)
            elif version in {"v13", "v14"}:
                schedule = _V13_SENKIN_SCHEDULE
            elif version == "v12":
                schedule = _V12_SYOUYA_SCHEDULE
            elif version in {"v10", "v11"}:
                schedule = _V10_SCHEDULE
            else:
                schedule = _FIXED_SCHEDULE
            step = min(max(0, int(_get(obs, "step", 0))), len(schedule) - 1)
            action = schedule[step]
            raw = (
                _v14_senkin_action(obs, step)
                if version == "v14"
                else _v13_senkin_action(obs, step)
                if version == "v13"
                else _v12_syouya_action(obs, step)
                if version == "v12"
                else action or {"farmer": ["PASS"], "hands": [], "market": []}
            )
            use_interference = (
                (version == "v12" and STRATEGY.get("v12_market_interference"))
                or (use_radiant and STRATEGY.get("v11_radiant_market_interference"))
                or (version not in {"v12", "v13", "v14"} and not use_radiant)
            )
            overlaid = (
                _apply_market_interference(obs, raw)
                if use_interference
                else _copy_action(raw)
            )
            return _apply_fixed_board_adaptation(obs, overlaid)
        _observe_opponent(obs)
        unit_actions = _assign_actions(obs)
        return {
            "farmer": unit_actions[0] if unit_actions else ["PASS"],
            "hands": unit_actions[1:],
            "market": _market_orders(obs),
        }
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
