{% extends "base.xml.tpl" %}
{% block backgroundcolor %}{% endblock %}
{% block headers %}
<onload>SetProperty(dropdown,1)</onload>
<defaultcontrol>100</defaultcontrol>
{% endblock %}
{% block controls %}
<control type="button" id="700">
    <!-- dummy for clicks off list -->
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>1080</height>
    <texturefocus>-</texturefocus>
    <texturenofocus>-</texturenofocus>
</control>
<control type="group" id="100">
    <defaultcontrol>250</defaultcontrol>
    <visible>!String.IsEmpty(Window.Property(show))</visible>
    <posx>0</posx>
    <posy>0</posy>
    <control type="image" id="110">
        <posx>-60</posx>
        <posy>{{ vperc(vscale(-106)) }}</posy>
        <width>720</width>
        <height>{{ vscale(146) }}</height>
        <texture border="42">script.plex/drop-shadow.png</texture>
    </control>
    <control type="group">
        <visible>!String.IsEmpty(Window.Property(header))</visible>
        <posx>-20</posx>
        <posy>{{ vscale(-66) }}</posy>
        <control type="image" id="111">
            <posx>0</posx>
            <posy>0</posy>
            <width>640</width>
            <height>{{ vscale(132) }}</height>
            <texture colordiffuse="D3111111" border="10">script.plex/white-square-rounded.png</texture>
        </control>
        <control type="label">
            <posx>20</posx>
            <posy>0</posy>
            <width>600</width>
            <height>{{ vscale(66) }}</height>
            <font>font12</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>FFEEEEEE</textcolor>
            <scroll>true</scroll>
            <scrollspeed>15</scrollspeed>
            <label>[B]$INFO[Window.Property(header)][/B]</label>
        </control>
    </control>
    <control type="list" id="250">
        <posx>0</posx>
        <posy>0</posy>
        <width>600</width>
        <height>{{ vscale(528) }}</height>
        <onup condition="String.IsEqual(Window.Property(close.direction),top)">Close</onup>
        <onup condition="!String.IsEqual(Window.Property(close.direction),top)">noop</onup>
        <onleft condition="String.IsEqual(Window.Property(close.direction),left)">Close</onleft>
        <onright condition="String.IsEqual(Window.Property(close.direction),right)">Close</onright>
        <ondown condition="String.IsEqual(Window.Property(close.direction),down)">Close</ondown>
        <ondown condition="!String.IsEqual(Window.Property(close.direction),down)">noop</ondown>
        <scrolltime>200</scrolltime>
        <orientation>vertical</orientation>
        <!-- ITEM LAYOUT ########################################## -->
        <itemlayout height="{{ vscale(66) }}">
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(first))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="99111111" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEmpty(ListItem.Property(first)) + String.IsEmpty(ListItem.Property(last)) + String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="99111111">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(last))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture flipy="true" colordiffuse="99111111" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="99111111" border="10">script.plex/white-square-rounded.png</texture>
            </control>
            <control type="label">
                <visible>String.IsEmpty(ListItem.Property(with.indicator)) + String.IsEqual(ListItem.Property(align),center)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>580</width>
                <height>{{ vscale(66) }}</height>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <scroll>true</scroll>
                <scrollspeed>20</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <visible>String.IsEmpty(ListItem.Property(with.indicator)) + String.IsEqual(ListItem.Property(align),left)</visible>
                <posx>20</posx>
                <posy>0</posy>
                <width>580</width>
                <height>{{ vscale(66) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <scroll>true</scroll>
                <scrollspeed>20</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="group">
                <visible>!String.IsEmpty(ListItem.Property(with.indicator))</visible>
                <control type="label">
                    <posx>60</posx>
                    <posy>0</posy>
                    <width>520</width>
                    <height>{{ vscale(66) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <scroll>true</scroll>
                    <scrollspeed>20</scrollspeed>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="image">
                    <posx>20</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>26</width>
                    <height>{{ vscale(26) }}</height>
                    <texture colordiffuse="FFFFFFFF">$INFO[ListItem.Thumb]</texture>
                    <aspectratio>keep</aspectratio>
                </control>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(separator))</visible>
                <posx>0</posx>
                <posy>{{ vscale(64) }}</posy>
                <width>600</width>
                <height>{{ vscale(2) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
        </itemlayout>
        <focusedlayout height="{{ vscale(66) }}">
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(first))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="F3E5A00D" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEmpty(ListItem.Property(first)) + String.IsEmpty(ListItem.Property(last)) + String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="F3E5A00D">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(last))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture flipy="true" colordiffuse="FFE5A00D" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>600</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texture>
            </control>
            <control type="label">
                <visible>String.IsEmpty(ListItem.Property(with.indicator)) + String.IsEqual(ListItem.Property(align),center)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>580</width>
                <height>{{ vscale(66) }}</height>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <scroll>true</scroll>
                <scrollspeed>20</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <visible>String.IsEmpty(ListItem.Property(with.indicator)) + String.IsEqual(ListItem.Property(align),left)</visible>
                <posx>20</posx>
                <posy>0</posy>
                <width>580</width>
                <height>{{ vscale(66) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <scroll>true</scroll>
                <scrollspeed>20</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="group">
                <visible>!String.IsEmpty(ListItem.Property(with.indicator))</visible>
                <control type="label">
                    <posx>60</posx>
                    <posy>0</posy>
                    <width>520</width>
                    <height>{{ vscale(66) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FF000000</textcolor>
                    <scroll>true</scroll>
                    <scrollspeed>20</scrollspeed>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="image">
                    <posx>20</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>26</width>
                    <height>{{ vscale(26) }}</height>
                    <texture colordiffuse="FF000000">$INFO[ListItem.Thumb]</texture>
                    <aspectratio>keep</aspectratio>
                </control>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(separator))</visible>
                <posx>0</posx>
                <posy>{{ vscale(64) }}</posy>
                <width>600</width>
                <height>{{ vscale(2) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
        </focusedlayout>
    </control>
</control>
{% endblock controls %}