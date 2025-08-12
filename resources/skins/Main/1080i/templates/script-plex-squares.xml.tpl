{% extends "library_posters.xml.tpl" %}
{% block filteropts_grouplist %}
<control type="grouplist">
<visible>String.IsEmpty(Window.Property(hide.filteroptions))</visible>
<right>340</right>
<posy>35</posy>
<width>1000</width>
<height>65</height>
<align>right</align>
<itemgap>30</itemgap>
<orientation>horizontal</orientation>
<onleft>204</onleft>
<onright>210</onright>
<ondown>50</ondown>
<control type="button" id="311">
    <enable>false</enable>
    <width max="300">auto</width>
    <height>65</height>
    <font>font12</font>
    <textcolor>FFFFFFFF</textcolor>
    <focusedcolor>FFFFFFFF</focusedcolor>
    <disabledcolor>FFFFFFFF</disabledcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturefocus>-</texturefocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>0</textoffsetx>
    <textoffsety>0</textoffsety>
    <label>[UPPERCASE]$INFO[Window.Property(filter2.display)][/UPPERCASE]</label>
</control>
<control type="button" id="211">
    <width max="500">auto</width>
    <height>65</height>
    <font>font12</font>
    <textcolor>FFFFFFFF</textcolor>
    <focusedcolor>FF000000</focusedcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>20</textoffsetx>
    <textoffsety>0</textoffsety>
    <label>[UPPERCASE]$INFO[Window.Property(filter1.display)][/UPPERCASE]</label>
</control>
<control type="button" id="310">
    <visible>!String.IsEqual(Window.Property(media),artist)</visible>
    <enable>false</enable>
    <width max="300">auto</width>
    <height>65</height>
    <font>font12</font>
    <textcolor>FFFFFFFF</textcolor>
    <focusedcolor>FFFFFFFF</focusedcolor>
    <disabledcolor>FFFFFFFF</disabledcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturenofocus>-</texturenofocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>20</textoffsetx>
    <textoffsety>0</textoffsety>
    <label>[UPPERCASE]$INFO[Window.Property(media.type)][/UPPERCASE]</label>
</control>
<control type="button" id="312">
    <visible>String.IsEqual(Window.Property(media),artist)</visible>
    <width max="300">auto</width>
    <height>65</height>
    <font>font12</font>
    <textcolor>FFFFFFFF</textcolor>
    <focusedcolor>FF000000</focusedcolor>
    <disabledcolor>FFFFFFFF</disabledcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>20</textoffsetx>
    <textoffsety>0</textoffsety>
    <label>[UPPERCASE]$INFO[Window.Property(media.type)][/UPPERCASE]</label>
</control>
<control type="button" id="210">
    <width max="300">auto</width>
    <height>65</height>
    <font>font12</font>
    <textcolor>FFFFFFFF</textcolor>
    <focusedcolor>FF000000</focusedcolor>
    <align>center</align>
    <aligny>center</aligny>
    <texturefocus colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texturefocus>
    <texturenofocus>-</texturenofocus>
    <textoffsetx>20</textoffsetx>
    <textoffsety>0</textoffsety>
    <label>[UPPERCASE]$INFO[Window.Property(sort.display)][/UPPERCASE]</label>
</control>
</control>
{% endblock filteropts_grouplist %}
{% block content %}
<control type="group" id="50">
    <animation effect="slide" time="200" end="0,{{ vscale(-135) }}" condition="Integer.IsGreater(Container(101).ListItem.Property(index),5)">Conditional</animation>
    <animation effect="slide" time="200" end="0,{{ vscale(-200) }}" condition="Integer.IsGreater(Container(101).ListItem.Property(index),5) + Integer.IsGreater(Container(101).Position,5)">Conditional</animation>
    <posx>0</posx>
    <posy>{{ vscale(135) }}</posy>
    <defaultcontrol>101</defaultcontrol>

    {% block buttons %}
        <control type="grouplist" id="300">
            <animation effect="fade" start="0" end="100" time="200" reversible="true">VisibleChange</animation>
            <visible>!Integer.IsGreater(Container(101).ListItem.Property(index),5) + String.IsEmpty(Window.Property(no.content)) + String.IsEmpty(Window.Property(no.content.filtered)) + !String.IsEmpty(Window.Property(initialized))</visible>
            <defaultcontrol>301</defaultcontrol>
            <posx>30</posx>
            <posy>{{ vscale(-25) }}</posy>
            <width>1000</width>
            <height>{{ vscale(145) }}</height>
            <onup>200</onup>
            <ondown>101</ondown>
            <itemgap>-20</itemgap>
            <orientation>horizontal</orientation>
            <scrolltime tween="quadratic" easing="out">200</scrolltime>
            <usecontrolcoords>true</usecontrolcoords>

            {% with attr = {"width": 126, "height": 100} & template = "includes/themed_button.xml.tpl" & hitrect = {"x": 20, "y": 20, "w": 86, "h": 60} %}
                {% include template with name="play" & id=301 & visible="String.IsEmpty(Window.Property(disable_playback)) + [!String.IsEqual(Window(10000).Property(script.plex.item.type),collection) | String.IsEqual(Window.Property(media),collection)]" %}
                {% include template with name="shuffle" & id=302 & visible="String.IsEmpty(Window.Property(disable_playback)) + [!String.IsEqual(Window(10000).Property(script.plex.item.type),collection) | String.IsEqual(Window.Property(media),collection)]" %}
                {% include template with name="more" & id=303 & visible="String.IsEmpty(Window.Property(disable_playback)) + [String.IsEmpty(Window.Property(no.options)) | Player.HasAudio]" %}
                {% include template with name="chapters" & id=304 & visible="String.IsEmpty(Window.Property(hide.filteroptions))" %}
            {% endwith %}

        </control>
    {% endblock %}

    <control type="group" id="100">
        <visible>Integer.IsGreater(Container(101).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
        <defaultcontrol>101</defaultcontrol>
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>1080</height>
        <control type="panel" id="101">
            <hitrect x="0" y="95" w="1780" h="1185" />
            <posx>0</posx>
            <posy>0</posy>
            <width>1800</width>
            <height>1280</height>
            <onup>300</onup>
            <onright>151</onright>
            <scrolltime>200</scrolltime>
            <orientation>vertical</orientation>
            <preloaditems>2</preloaditems>
            <pagecontrol>152</pagecontrol>
            <!-- ITEM LAYOUT ########################################## -->
            <itemlayout width="287" height="{{ vscale(343) }}">
                <control type="group">
                    <posx>55</posx>
                    <posy>{{ vscale(97) }}</posy>
                    <control type="group">
                        <posx>5</posx>
                        <posy>5</posy>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>244</width>
                            <height>{{ vscale(244) }}</height>
                            <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
                        </control>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>244</width>
                            <height>{{ vscale(244) }}</height>
                            <texture background="true">$INFO[ListItem.Thumb]</texture>
                            <aspectratio>scale</aspectratio>
                        </control>
                        <control type="image">
                            <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                            <posx>0</posx>
                            <posy>{{ vscale(244) }}</posy>
                            <width>244</width>
                            <height>{{ vscale(40) }}</height>
                            <texture>script.plex/white-square.png</texture>
                            <colordiffuse>80000000</colordiffuse>
                        </control>
                        <control type="label">
                            <scroll>true</scroll>
                            <posx>0</posx>
                            <posy>{{ vscale(244) }}</posy>
                            <width>244</width>
                            <height>{{ vscale(40) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>FFFFFFFF</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </control>
                </control>
            </itemlayout>

            <!-- FOCUSED LAYOUT ####################################### -->
            <focusedlayout width="287" height="{{ vscale(343) }}">
                <control type="group">
                    <posx>55</posx>
                    <posy>{{ vscale(97) }}</posy>
                    <control type="group">
                        <animation effect="zoom" start="100" end="110" time="100" center="127,{{ vscale(127) }}" reversible="false">Focus</animation>
                        <animation effect="zoom" start="110" end="100" time="100" center="127,{{ vscale(127) }}" reversible="false">UnFocus</animation>
                        <posx>0</posx>
                        <posy>0</posy>
                        <control type="group">
                            <visible>Control.HasFocus(101)</visible>
                            <control type="image">
                                <visible>String.IsEmpty(ListItem.Property(is.folder))</visible>
                                <posx>-40</posx>
                                <posy>{{ vscale(-40) }}</posy>
                                <width>334</width>
                                <height>{{ vscale(334) }}</height>
                                <texture border="42">script.plex/drop-shadow.png</texture>
                            </control>
                            <control type="image">
                                <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                                <posx>-40</posx>
                                <posy>{{ vscale(-40) }}</posy>
                                <width>334</width>
                                <height>{{ vscale(374) }}</height>
                                <texture border="42">script.plex/drop-shadow.png</texture>
                            </control>
                        </control>
                        <control type="group">
                            <posx>5</posx>
                            <posy>5</posy>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>244</width>
                                <height>{{ vscale(244) }}</height>
                                <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>244</width>
                                <height>{{ vscale(244) }}</height>
                                <texture background="true">$INFO[ListItem.Thumb]</texture>
                                <aspectratio>scale</aspectratio>
                            </control>
                            <control type="image">
                                <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                                <posx>0</posx>
                                <posy>{{ vscale(244) }}</posy>
                                <width>244</width>
                                <height>{{ vscale(40) }}</height>
                                <texture>script.plex/white-square.png</texture>
                                <colordiffuse>80000000</colordiffuse>
                            </control>
                            <control type="label">
                                <scroll>Control.HasFocus(101)</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(244) }}</posy>
                                <width>244</width>
                                <height>{{ vscale(40) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <aligny>center</aligny>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                        </control>
                        <control type="group">
                            <visible>Control.HasFocus(101)</visible>
                            <control type="image">
                                <visible>String.IsEmpty(ListItem.Property(is.folder))</visible>
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>254</width>
                                <height>{{ vscale(254) }}</height>
                                <texture border="10">script.plex/home/selected.png</texture>
                            </control>
                            <control type="image">
                                <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>254</width>
                                <height>{{ vscale(294) }}</height>
                                <texture border="10">script.plex/home/selected.png</texture>
                            </control>
                        </control>
                    </control>
                </control>
            </focusedlayout>
        </control>
    </control>
</control>

<control type="group" id="150">
    <visible>String.IsEqual(Window(10000).Property(script.plex.sort),titleSort) + Integer.IsGreater(Container(101).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
    <defaultcontrol>151</defaultcontrol>
    <posx>1780</posx>
    <posy>{{ vscale(150) }}</posy>
    <width>20</width>
    <height>920</height>
    <control type="list" id="151">
        <posx>0</posx>
        <posy>0</posy>
        <width>34</width>
        <height>1050</height>
        <onleft>100</onleft>
        <onright>152</onright>
        <scrolltime>200</scrolltime>
        <orientation>vertical</orientation>
        <!-- ITEM LAYOUT ########################################## -->
        <itemlayout height="34">
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="group">
                    <posx>0</posx>
                    <posy>0</posy>
                    <control type="label">
                        <visible>!String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(letter))</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>34</width>
                        <height>{{ vscale(32) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>99FFFFFF</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(key))</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>34</width>
                        <height>{{ vscale(32) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>FFE5A00D</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                </control>
            </control>
        </itemlayout>

        <!-- FOCUSED LAYOUT ####################################### -->
        <focusedlayout height="34">
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="group">
                    <posx>0</posx>
                    <posy>0</posy>
                    <control type="label">
                        <visible>!String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(letter))</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>34</width>
                        <height>{{ vscale(32) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>99FFFFFF</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                    <control type="label">
                        <visible>String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(key))</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>34</width>
                        <height>{{ vscale(32) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>FFE5A00D</textcolor>
                        <label>$INFO[ListItem.Label]</label>
                    </control>
                </control>

                <control type="group">
                    <visible>Control.HasFocus(151)</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <control type="image">
                        <visible>Control.HasFocus(151)</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <width>34</width>
                        <height>{{ vscale(34) }}</height>
                        <colordiffuse>FFE5A00D</colordiffuse>
                        <texture border="12">script.plex/white-outline-rounded.png</texture>
                    </control>
                </control>
            </control>
        </focusedlayout>
    </control>
</control>

<control type="scrollbar" id="152">
    <hitrect x="1820" y="150" w="100" h="910" />
    <left>1860</left>
    <top>{{ vscale(150) }}</top>
    <width>12</width>
    <height>910</height>
    <visible>true</visible>
    <texturesliderbackground colordiffuse="40000000" border="5">script.plex/white-square-rounded.png</texturesliderbackground>
    <texturesliderbar colordiffuse="77FFFFFF" border="5">script.plex/white-square-rounded.png</texturesliderbar>
    <texturesliderbarfocus colordiffuse="FFE5A00D" border="5">script.plex/white-square-rounded.png</texturesliderbarfocus>
    <textureslidernib>-</textureslidernib>
    <textureslidernibfocus>-</textureslidernibfocus>
    <pulseonselect>false</pulseonselect>
    <orientation>vertical</orientation>
    <showonepage>false</showonepage>
    <onleft>151</onleft>
</control>
{% endblock content %}