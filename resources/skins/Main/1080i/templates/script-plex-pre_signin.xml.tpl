{% extends "base.xml.tpl" %}
{% block headers %}<defaultcontrol>100</defaultcontrol>{% endblock %}
{% block controls %}
<control type="image">
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>1080</height>
    <texture background="true">script.plex/home/background-fallback_black.png</texture>
</control>
<control type="image">
    <posx>0</posx>
    <posy>{% if core.needs_scaling %}{{ vperc(vscale(1080)) }}{% else %}0{% endif %}</posy>
    <width>1920</width>
    <height>{{ vscale(1080) }}</height>
    <texture>script.plex/sign_in/pre-signin.jpg</texture>
</control>

<control type="button" id="100">
    <posx>1437</posx>
    <posy>{{ vperc(vscale(1080)) + vscale(1080) - vscale(279) }}</posy>
    <width>275</width>
    <height>{{ vscale(104) }}</height>
    <onup>200</onup>
    <ondown>101</ondown>
    <font>font13</font>
    <textcolor>FFFFFFFF</textcolor>
    <focusedcolor>FFFFFFFF</focusedcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturefocus>-</texturefocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>0</textoffsetx>
    <textoffsety>0</textoffsety>
    <label> </label>
</control>

<control type="button" id="101">
    <posx>1437</posx>
    <posy>{{ vperc(vscale(1080)) + vscale(1080) - vscale(165) }}</posy>
    <width>275</width>
    <height>{{ vscale(70) }}</height>
    <onup>100</onup>
    <font>font12</font>
    <textcolor>B3FFFFFF</textcolor>
    <focusedcolor>FFFFFFFF</focusedcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturefocus>-</texturefocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>0</textoffsetx>
    <textoffsety>0</textoffsety>
    <label>$ADDON[script.plexmod 35022]</label>
</control>
{% endblock controls %}