"""Approximate preview swatches inferred visually from the supplied color chart.

These are not measured AVEVA RGB values. Export always uses the original number.
"""
import colorsys


def _hex(hue,saturation,value):
    rgb=colorsys.hsv_to_rgb(hue/360,saturation,value)
    return '#'+''.join(f'{round(channel*255):02x}' for channel in rgb)


def _palette():
    values={}
    first=['#77766e','#b92b34','#e69722','#eed522','#278c53','#2999ad','#253f86','#d8799b','#724629','#f6f0df',
           '#a65e61','#542346','#1699a5','#25203b','#171817','#d31a70','#141514','#d42029','#ece119','#238748',
           '#299dab','#243c71','#c82070','#f3ecdf','#45453e','#aaa69b','#db1627','#e79583','#a92730','#a74e51']
    values.update({i+1:color for i,color in enumerate(first)})
    hues=[5,12,23,35,48,70,100,130,148,160,173,183,193,207,224,241,258,279,309,335,349,358,8,20]
    shades=[(.56,.40),(.20,.44),(.73,.33),(.27,.35),(.70,.25),(.16,.29),(.88,.82),(.28,.91),(.73,.56),(.32,.63)]
    for row,hue in enumerate(hues,3):
        for col,(saturation,value) in enumerate(shades,1):values[row*10+col]=_hex(hue,saturation,value)
    extras=['#a7a69e','#f2eee2','#ebe7de','#f6f0e3','#f2eddd','#ece7d8','#ddd7c9','#e3ddca','#cfc8b5','#b9b09b',
            '#de7296','#a24958','#635561','#73605d','#278b80','#bd1558','#e9a43e','#d71977','#a02027','#c52b37',
            '#ac4c46','#c81965','#eee9d9','#3d5f83','#e7e0c5','#284358','#e5dfc9','#e3d489','#f6f1de','#12142b',
            '#f5efdf','#eadd70','#e99b36','#eee5d0','#171712','#e4ddc4','#eee7d5','#e2d372','#72645b','#b7aa8a',
            '#777d6c','#354f3c','#ae303a','#de706d','#751f24','#a01929','#78455b','#c91f50','#b47778','#ab5050']
    values.update({271+i:color for i,color in enumerate(extras)})
    return values


PREVIEW_COLORS=_palette()


def preview_color(number):
    try:return PREVIEW_COLORS.get(int(number))
    except (ValueError,TypeError):return None


def foreground_color(color):
    rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    return '#ffffff' if sum(channel*weight for channel,weight in zip(rgb,(.2126,.7152,.0722)))<.48 else '#17202b'
