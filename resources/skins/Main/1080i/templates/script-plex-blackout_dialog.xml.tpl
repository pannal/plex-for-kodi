{% extends "base.xml.tpl" %}
{% block headers %}
    <defaultcontrol>800</defaultcontrol>
    <zorder>101</zorder>
{% endblock %}
{% block backgroundcolor %}{% endblock %}

{% block controls %}
<control type="group" id="804">
    <animation effect="fade" time="200" delay="200" end="0">WindowClose</animation>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>1080</height>
        <texture>script.plex/white-square.png</texture>
        <colordiffuse>FF000000</colordiffuse>
    </control>
</control>
{% endblock %}