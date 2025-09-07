{% extends "default.xml.tpl" %}
{% block header %}
<control type="group">
    <visible>!String.IsEmpty(Window.Property(post.play))</visible>
    {{ super() }}
</control>
{% endblock header %}

{% block content %}
<control type="group">
    <visible>!String.IsEmpty(Window.Property(post.play))</visible>
    <control type="group">
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>1080</height>
            <texture background="true">$INFO[Window.Property(post.play.background)]</texture>
            {% include "includes/scale_background.xml.tpl" %}
        </control>
    </control>

    <control type="group" id="50">
        <animation effect="slide" end="0,{{ vscale(-300) }}" time="200" tween="quadratic" easing="out" condition="!String.IsEmpty(Window.Property(on.extras))">Conditional</animation>

        <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),0) + Control.IsVisible(500)" reversible="true">
            <effect type="slide" end="0,{{ vscale(-500) }}" time="200" tween="quadratic" easing="out"/>
        </animation>

        <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),1) + Control.IsVisible(501)" reversible="true">
            <effect type="slide" end="0,{{ vscale(-500) }}" time="200" tween="quadratic" easing="out"/>
        </animation>

        <posx>0</posx>
        <posy>{{ vscale(135) }}</posy>
        <defaultcontrol>102</defaultcontrol>

        <control type="image">
            <posx>60</posx>
            <posy>0</posy>
            <width>1800</width>
            <height>{{ vscale(2) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>A0000000</colordiffuse>
        </control>

        <control type="label">
            <scroll>false</scroll>
            <posx>60</posx>
            <posy>{{ vscale(57) }}</posy>
            <width>462</width>
            <height>{{ vscale(40) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>A0FFFFFF</textcolor>
            <label>[UPPERCASE]$ADDON[script.plexmod 32438][/UPPERCASE]</label>
        </control>

        <control type="group" id="100">
            <defaultcontrol>102</defaultcontrol>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <width>1920</width>
                <height>{{ vscale(580) }}</height>
                <control type="group">
                    <posx>60</posx>
                    <posy>{{ vscale(131) }}</posy>
                    <control type="group">
                        <animation effect="zoom" start="100" end="110" time="100" center="231,{{ vscale(129.5) }}" reversible="true" condition="Control.HasFocus(101)">Conditional</animation>
                        <posx>0</posx>
                        <posy>0</posy>
                        <control type="image">
                            <visible>Control.HasFocus(101)</visible>
                            <posx>-45</posx>
                            <posy>{{ vscale(-45) }}</posy>
                            <width>552</width>
                            <height>{{ vscale(349) }}</height>
                            <texture border="42">script.plex/drop-shadow.png</texture>
                        </control>
                        <control type="group">
                            <posx>0</posx>
                            <posy>0</posy>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>462</width>
                                <height>{{ vscale(259) }}</height>
                                <texture>$INFO[Window.Property(thumb.fallback)]</texture>
                                <aspectratio>scale</aspectratio>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>462</width>
                                <height>{{ vscale(259) }}</height>
                                <texture background="true">$INFO[Window.Property(prev.thumb)]</texture>
                                <aspectratio>scale</aspectratio>
                            </control>
                            <control type="group">
                                <posx>193</posx>
                                <posy>{{ vscale(91.5) }}</posy>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>76</width>
                                    <height>{{ vscale(76) }}</height>
                                    <texture colordiffuse="99000000">script.plex/indicators/circle-152.png</texture>
                                </control>
                                <control type="image">
                                    <posx>15</posx>
                                    <posy>{{ vscale(15) }}</posy>
                                    <width>46</width>
                                    <height>{{ vscale(46) }}</height>
                                    <texture>script.plex/indicators/replay.png</texture>
                                </control>
                            </control>
                            <control type="label">
                                <scroll>true</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(269) }}</posy>
                                <width>462</width>
                                <height>{{ vscale(35) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>$INFO[Window.Property(prev.title)]</label>
                            </control>
                            <control type="label">
                                <scroll>true</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(301) }}</posy>
                                <width>462</width>
                                <height>{{ vscale(35) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>$INFO[Window.Property(prev.subtitle)]</label>
                            </control>
                        </control>
                        <control type="button" id="101">
                            <posx>-5</posx>
                            <posy>{{ vscale(-5) }}</posy>
                            <width>472</width>
                            <height>{{ vscale(269) }}</height>
                            <onup>200</onup>
                            <ondown>400</ondown>
                            <onright>102</onright>
                            <texturefocus border="10">script.plex/home/selected.png</texturefocus>
                            <texturenofocus>-</texturenofocus>
                        </control>
                    </control>
                </control>

                <control type="group">
                    <visible>!String.IsEmpty(Window.Property(has.next))</visible>
                    <control type="label">
                        <scroll>false</scroll>
                        <posx>572</posx>
                        <posy>{{ vscale(57) }}</posy>
                        <width>462</width>
                        <height>{{ vscale(40) }}</height>
                        <font>font12</font>
                        <align>left</align>
                        <aligny>center</aligny>
                        <textcolor>FFFFFFFF</textcolor>
                        <label>[UPPERCASE]$ADDON[script.plexmod 32439][/UPPERCASE]</label>
                    </control>
                    <control type="group">
                        <posx>582</posx>
                        <posy>{{ vscale(131) }}</posy>
                        <control type="group">
                            <animation effect="zoom" start="100" end="110" time="100" center="268.5,{{ vscale(151.5) }}" reversible="true" condition="Control.HasFocus(102)">Conditional</animation>
                            <posx>0</posx>
                            <posy>0</posy>
                            <control type="image">
                                <visible>Control.HasFocus(102)</visible>
                                <posx>-45</posx>
                                <posy>{{ vscale(-45) }}</posy>
                                <width>627</width>
                                <height>{{ vscale(393) }}</height>
                                <texture border="42">script.plex/drop-shadow.png</texture>
                            </control>
                            <control type="group">
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>537</width>
                                    <height>{{ vscale(303) }}</height>
                                    <texture>$INFO[Window.Property(thumb.fallback)]</texture>
                                    <aspectratio>scale</aspectratio>
                                </control>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>537</width>
                                    <height>{{ vscale(303) }}</height>
                                    <texture background="true">$INFO[Window.Property(next.thumb)]</texture>
                                    <aspectratio>scale</aspectratio>
                                </control>
                                <control type="group">
                                    <visible>!String.IsEmpty(Window.Property(countdown)) + Integer.IsGreaterOrEqual(Window.Property(countdown), 0)</visible>
                                    <posx>192.5</posx>
                                    <posy>{{ vscale(75.5) }}</posy>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>152</width>
                                        <height>{{ vscale(152) }}</height>
                                        <texture colordiffuse="99000000">script.plex/indicators/circle-152.png</texture>
                                    </control>
                                    <control type="image">
                                        <posx>8</posx>
                                        <posy>8</posy>
                                        <width>136</width>
                                        <height>{{ vscale(136) }}</height>
                                        <texture colordiffuse="FFCC7B19">script.plex/circle-progress/$INFO[Window.Property(countdown)].png</texture>
                                    </control>
                                    <control type="image">
                                        <posx>59.5</posx>
                                        <posy>{{ vscale(57) }}</posy>
                                        <width>33</width>
                                        <height>{{ vscale(38) }}</height>
                                        <texture>script.plex/indicators/pause.png</texture>
                                    </control>
                                </control>
                                <control type="label">
                                    <scroll>true</scroll>
                                    <posx>0</posx>
                                    <posy>{{ vscale(313) }}</posy>
                                    <width>537</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[Window.Property(next.title)]</label>
                                </control>
                                <control type="label">
                                    <scroll>true</scroll>
                                    <posx>0</posx>
                                    <posy>{{ vscale(345) }}</posy>
                                    <width>537</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[Window.Property(next.subtitle)]</label>
                                </control>
                            </control>
                            <control type="button" id="102">
                                <posx>-5</posx>
                                <posy>{{ vscale(-5) }}</posy>
                                <width>547</width>
                                <height>{{ vscale(313) }}</height>
                                <onup>200</onup>
                                <ondown>400</ondown>
                                <onleft>101</onleft>
                                <texturefocus border="10">script.plex/home/selected.png</texturefocus>
                                <texturenofocus>-</texturenofocus>
                            </control>
                        </control>
                    </control>
                </control>
            </control>

            <control type="group">
                <visible>!String.IsEmpty(Window.Property(has.next))</visible>
                <control type="label">
                    <scroll>true</scroll>
                    <posx>1177</posx>
                    <posy>{{ vscale(131) }}</posy>
                    <width>683</width>
                    <height>{{ vscale(43) }}</height>
                    <font>font13</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>[B]$INFO[Window.Property(info.title)][/B]</label>
                </control>
                <control type="label">
                    <scroll>false</scroll>
                    <posx>1177</posx>
                    <posy>{{ vscale(189) }}</posy>
                    <width>683</width>
                    <height>{{ vscale(32) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>A0FFFFFF</textcolor>
                    <label>$INFO[Window.Property(info.date)]$INFO[Window.Property(info.duration), &#8226; ]</label>
                </control>
                <control type="textbox">
                    <autoscroll delay="2000" time="2000" repeat="10000"></autoscroll>
                    <posx>1177</posx>
                    <posy>{{ vscale(240) }}</posy>
                    <width>683</width>
                    <height>{{ vscale(215) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[Window.Property(info.summary)]</label>
                </control>
            </control>

            <control type="group">
                <visible>String.IsEmpty(Window.Property(has.next))</visible>
                <control type="label">
                    <scroll>true</scroll>
                    <posx>580</posx>
                    <posy>{{ vscale(131) }}</posy>
                    <width>1280</width>
                    <height>{{ vscale(43) }}</height>
                    <font>font13</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>[B]$INFO[Window.Property(prev.info.title)][/B]</label>
                </control>
                <control type="label">
                    <scroll>false</scroll>
                    <posx>580</posx>
                    <posy>{{ vscale(189) }}</posy>
                    <width>1280</width>
                    <height>{{ vscale(32) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>A0FFFFFF</textcolor>
                    <label>$INFO[Window.Property(prev.info.date)]$INFO[Window.Property(prev.info.duration), &#8226; ]</label>
                </control>
                <control type="textbox">
                    <autoscroll delay="2000" time="2000" repeat="10000"></autoscroll>
                    <posx>580</posx>
                    <posy>{{ vscale(240) }}</posy>
                    <width>1280</width>
                    <height>{{ vscale(225) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[Window.Property(prev.info.summary)]</label>
                </control>
            </control>
        </control>

        <control type="grouplist" id="60">
            <posx>0</posx>
            <posy>{{ vscale(530) }}</posy>
            <width>1920</width>
            <height>{{ vscale(1610) }}</height>

            <onup>300</onup>
            <itemgap>0</itemgap>

            <control type="group" id="500">
                <visible>Integer.IsGreater(Container(400).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
                <height>{{ vscale(360) }}</height>
                <width>1920</width>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>1920</width>
                    <height>{{ vscale(360) }}</height>
                    <texture>script.plex/white-square.png</texture>
                    <colordiffuse>40000000</colordiffuse>
                </control>
                <control type="label">
                    <posx>60</posx>
                    <posy>0</posy>
                    <width>800</width>
                    <height>{{ vscale(80) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>[UPPERCASE]$ADDON[script.plexmod 32440][/UPPERCASE]</label>
                </control>
                <control type="list" id="400">
                    <posx>0</posx>
                    <posy>{{ vscale(18) }}</posy>
                    <width>1920</width>
                    <height>{{ vscale(430) }}</height>
                    <onup>100</onup>
                    <ondown>401</ondown>
                    <onleft>noop</onleft>
                    <onright>noop</onright>
                    <scrolltime>200</scrolltime>
                    <orientation>horizontal</orientation>
                    <preloaditems>4</preloaditems>
                    <!-- ITEM LAYOUT ########################################## -->
                    <itemlayout width="359">
                        <control type="group">
                            <posx>55</posx>
                            <posy>{{ vscale(61) }}</posy>
                            <control type="group">
                                <posx>5</posx>
                                <posy>5</posy>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>299</width>
                                    <height>{{ vscale(168) }}</height>
                                    <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
                                    <aspectratio>scale</aspectratio>
                                </control>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>299</width>
                                    <height>{{ vscale(168) }}</height>
                                    <texture background="true">$INFO[ListItem.Thumb]</texture>
                                    <aspectratio>scale</aspectratio>
                                </control>
                                <control type="group">
                                    <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                                    <posx>0</posx>
                                    <posy>{{ vscale(158) }}</posy>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>299</width>
                                        <height>{{ vscale(10) }}</height>
                                        <texture>script.plex/white-square.png</texture>
                                        <colordiffuse>C0000000</colordiffuse>
                                    </control>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>1</posy>
                                        <width>299</width>
                                        <height>{{ vscale(8) }}</height>
                                        <texture>$INFO[ListItem.Property(progress)]</texture>
                                        <colordiffuse>FFCC7B19</colordiffuse>
                                    </control>
                                </control>
                                {% include "includes/watched_indicator.xml.tpl" with xoff=299 & uw_size=35 & wbg_w=40 & wbg_h=32 %}

                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>0</posx>
                                    <posy>{{ vscale(180) }}</posy>
                                    <width>299</width>
                                    <height>{{ vscale(35) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                </control>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>0</posx>
                                    <posy>{{ vscale(212) }}</posy>
                                    <width>299</width>
                                    <height>{{ vscale(35) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                </control>
                                <control type="group">
                                    <visible>!String.IsEmpty(ListItem.Property(is.boundary))</visible>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>299</width>
                                        <height>{{ vscale(168) }}</height>
                                        <texture colordiffuse="FF404040">script.plex/white-square.png</texture>
                                    </control>
                                    <control type="image">
                                        <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(right.boundary))</visible>
                                        <posx>119</posx>
                                        <posy>{{ vscale(34) }}</posy>
                                        <width>61</width>
                                        <height>{{ vscale(100) }}</height>
                                        <texture colordiffuse="40000000">script.plex/indicators/chevron-white.png</texture>
                                    </control>
                                    <control type="image">
                                        <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(left.boundary))</visible>
                                        <posx>119</posx>
                                        <posy>{{ vscale(34) }}</posy>
                                        <width>61</width>
                                        <height>{{ vscale(100) }}</height>
                                        <texture colordiffuse="40000000">script.plex/indicators/chevron-white-l.png</texture>
                                    </control>
                                    <control type="image">
                                        <visible>!String.IsEmpty(ListItem.Property(is.updating))</visible>
                                        <posx>85.5</posx>
                                        <posy>{{ vscale(20) }}</posy>
                                        <width>128</width>
                                        <height>{{ vscale(128) }}</height>
                                        <texture>script.plex/home/busy.gif</texture>
                                    </control>
                                </control>
                            </control>
                        </control>
                    </itemlayout>

                    <!-- FOCUSED LAYOUT ####################################### -->
                    <focusedlayout width="359">
                        <control type="group">
                            <posx>55</posx>
                            <posy>{{ vscale(61) }}</posy>
                            <control type="group">
                                <animation effect="zoom" start="100" end="110" time="100" center="154.5,{{ vscale(87.5) }}" reversible="false">Focus</animation>
                                <animation effect="zoom" start="110" end="100" time="100" center="154.5,{{ vscale(87.5) }}" reversible="false">UnFocus</animation>
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="image">
                                    <visible>Control.HasFocus(400)</visible>
                                    <posx>-40</posx>
                                    <posy>{{ vscale(-40) }}</posy>
                                    <width>389</width>
                                    <height>{{ vscale(258) }}</height>
                                    <texture border="42">script.plex/drop-shadow.png</texture>
                                </control>
                                <control type="group">
                                    <posx>5</posx>
                                    <posy>5</posy>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>299</width>
                                        <height>{{ vscale(168) }}</height>
                                        <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
                                        <aspectratio>scale</aspectratio>
                                    </control>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>299</width>
                                        <height>{{ vscale(168) }}</height>
                                        <texture background="true">$INFO[ListItem.Thumb]</texture>
                                        <aspectratio>scale</aspectratio>
                                    </control>
                                    <control type="group">
                                        <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                                        <posx>0</posx>
                                        <posy>{{ vscale(158) }}</posy>
                                        <control type="image">
                                            <posx>0</posx>
                                            <posy>0</posy>
                                            <width>299</width>
                                            <height>{{ vscale(10) }}</height>
                                            <texture>script.plex/white-square.png</texture>
                                            <colordiffuse>C0000000</colordiffuse>
                                        </control>
                                        <control type="image">
                                            <posx>0</posx>
                                            <posy>1</posy>
                                            <width>299</width>
                                            <height>{{ vscale(8) }}</height>
                                            <texture>$INFO[ListItem.Property(progress)]</texture>
                                            <colordiffuse>FFCC7B19</colordiffuse>
                                        </control>
                                    </control>
                                    {% include "includes/watched_indicator.xml.tpl" with xoff=299 & uw_size=35 & wbg_w=40 & wbg_h=32 %}
                                    <control type="label">
                                        <scroll>false</scroll>
                                        <posx>0</posx>
                                        <posy>{{ vscale(180) }}</posy>
                                        <width>299</width>
                                        <height>{{ vscale(35) }}</height>
                                        <font>font10</font>
                                        <align>center</align>
                                        <textcolor>FFFFFFFF</textcolor>
                                        <label>$INFO[ListItem.Label]</label>
                                    </control>
                                    <control type="label">
                                        <scroll>false</scroll>
                                        <posx>0</posx>
                                        <posy>{{ vscale(212) }}</posy>
                                        <width>299</width>
                                        <height>{{ vscale(35) }}</height>
                                        <font>font10</font>
                                        <align>center</align>
                                        <textcolor>FFFFFFFF</textcolor>
                                        <label>$INFO[ListItem.Label2]</label>
                                    </control>
                                    <control type="group">
                                        <visible>!String.IsEmpty(ListItem.Property(is.boundary))</visible>
                                        <control type="image">
                                            <posx>0</posx>
                                            <posy>0</posy>
                                            <width>299</width>
                                            <height>{{ vscale(168) }}</height>
                                            <texture colordiffuse="FF404040">script.plex/white-square.png</texture>
                                        </control>
                                        <control type="image">
                                            <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(right.boundary))</visible>
                                            <posx>119</posx>
                                            <posy>{{ vscale(34) }}</posy>
                                            <width>61</width>
                                            <height>{{ vscale(100) }}</height>
                                            <texture colordiffuse="40000000">script.plex/indicators/chevron-white.png</texture>
                                        </control>
                                        <control type="image">
                                            <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(left.boundary))</visible>
                                            <posx>119</posx>
                                            <posy>{{ vscale(34) }}</posy>
                                            <width>61</width>
                                            <height>{{ vscale(100) }}</height>
                                            <texture colordiffuse="40000000">script.plex/indicators/chevron-white-l.png</texture>
                                        </control>
                                        <control type="image">
                                            <visible>!String.IsEmpty(ListItem.Property(is.updating))</visible>
                                            <posx>85.5</posx>
                                            <posy>{{ vscale(20) }}</posy>
                                            <width>128</width>
                                            <height>{{ vscale(128) }}</height>
                                            <texture>script.plex/home/busy.gif</texture>
                                        </control>
                                    </control>
                                </control>
                                <control type="image">
                                    <visible>Control.HasFocus(400)</visible>
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>309</width>
                                    <height>{{ vscale(178) }}</height>
                                    <texture border="10">script.plex/home/selected.png</texture>
                                </control>
                            </control>
                        </control>
                    </focusedlayout>
                </control>
            </control>

            <control type="group" id="501">
                <visible>Integer.IsGreater(Container(401).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
                <defaultcontrol>401</defaultcontrol>
                <width>1920</width>
                <height>{{ vscale(520) }}</height>
                <control type="label">
                    <posx>60</posx>
                    <posy>0</posy>
                    <width>1000</width>
                    <height>{{ vscale(80) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>[UPPERCASE]$INFO[Window.Property(related.header)][/UPPERCASE]</label>
                </control>
                <control type="list" id="401">
                    <posx>0</posx>
                    <posy>{{ vscale(16) }}</posy>
                    <width>1920</width>
                    <height>{{ vscale(520) }}</height>
                    <onup>400</onup>
                    <ondown>403</ondown>
                    <onleft>noop</onleft>
                    <onright>noop</onright>
                    <scrolltime>200</scrolltime>
                    <orientation>horizontal</orientation>
                    <preloaditems>4</preloaditems>
                    <!-- ITEM LAYOUT ########################################## -->
                    <itemlayout width="304">
                        <control type="group">
                            <posx>55</posx>
                            <posy>{{ vscale(72) }}</posy>
                            <control type="group">
                                <posx>5</posx>
                                <posy>5</posy>
                                <control type="group">
                                    <visible>!String.IsEmpty(ListItem.Property(is.boundary))</visible>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(361) }}</height>
                                        <texture colordiffuse="FF404040">script.plex/white-square.png</texture>
                                    </control>
                                    <control type="image">
                                        <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(right.boundary))</visible>
                                        <posx>91.5</posx>
                                        <posy>{{ vscale(130.5) }}</posy>
                                        <width>61</width>
                                        <height>{{ vscale(100) }}</height>
                                        <texture colordiffuse="40000000">script.plex/indicators/chevron-white.png</texture>
                                    </control>
                                    <control type="image">
                                        <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(left.boundary))</visible>
                                        <posx>91.5</posx>
                                        <posy>{{ vscale(130.5) }}</posy>
                                        <width>61</width>
                                        <height>{{ vscale(100) }}</height>
                                        <texture colordiffuse="40000000">script.plex/indicators/chevron-white-l.png</texture>
                                    </control>
                                    <control type="image">
                                        <visible>!String.IsEmpty(ListItem.Property(is.updating))</visible>
                                        <posx>58</posx>
                                        <posy>{{ vscale(116.5) }}</posy>
                                        <width>128</width>
                                        <height>{{ vscale(128) }}</height>
                                        <texture>script.plex/home/busy.gif</texture>
                                    </control>
                                </control>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>244</width>
                                    <height>{{ vscale(361) }}</height>
                                    <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
                                </control>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>244</width>
                                    <height>{{ vscale(361) }}</height>
                                    <texture background="true">$INFO[ListItem.Thumb]</texture>
                                    <aspectratio>scale</aspectratio>
                                </control>
                                <control type="group">
                                    <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                                    <posx>0</posx>
                                    <posy>{{ vscale(351) }}</posy>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(10) }}</height>
                                        <texture>script.plex/white-square.png</texture>
                                        <colordiffuse>C0000000</colordiffuse>
                                    </control>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>1</posy>
                                        <width>244</width>
                                        <height>{{ vscale(8) }}</height>
                                        <texture>$INFO[ListItem.Property(progress)]</texture>
                                        <colordiffuse>FFCC7B19</colordiffuse>
                                    </control>
                                </control>
                                {% include "includes/watched_indicator.xml.tpl" with xoff=244 & uw_size=48 & with_count=True & scale="medium" %}

                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>0</posx>
                                    <posy>{{ vscale(369) }}</posy>
                                    <width>244</width>
                                    <height>{{ vscale(38) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                </control>
                            </control>
                        </control>
                    </itemlayout>

                    <!-- FOCUSED LAYOUT ####################################### -->
                    <focusedlayout width="304">
                        <control type="group">
                            <posx>55</posx>
                            <posy>{{ vscale(72) }}</posy>
                            <control type="group">
                                <animation effect="zoom" start="100" end="110" time="100" center="127,{{ vscale(180.5) }}" reversible="false">Focus</animation>
                                <animation effect="zoom" start="110" end="100" time="100" center="127,{{ vscale(180.5) }}" reversible="false">UnFocus</animation>
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="image">
                                    <visible>Control.HasFocus(401)</visible>
                                    <posx>-40</posx>
                                    <posy>{{ vscale(-40) }}</posy>
                                    <width>324</width>
                                    <height>{{ vscale(441) }}</height>
                                    <texture border="42">script.plex/drop-shadow.png</texture>
                                </control>
                                <control type="group">
                                    <posx>5</posx>
                                    <posy>5</posy>
                                    <control type="group">
                                        <visible>!String.IsEmpty(ListItem.Property(is.boundary))</visible>
                                        <control type="image">
                                            <posx>0</posx>
                                            <posy>0</posy>
                                            <width>244</width>
                                            <height>{{ vscale(361) }}</height>
                                            <texture colordiffuse="FF404040">script.plex/white-square.png</texture>
                                        </control>
                                        <control type="image">
                                            <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(right.boundary))</visible>
                                            <posx>91.5</posx>
                                            <posy>{{ vscale(130.5) }}</posy>
                                            <width>61</width>
                                            <height>{{ vscale(100) }}</height>
                                            <texture colordiffuse="40000000">script.plex/indicators/chevron-white.png</texture>
                                        </control>
                                        <control type="image">
                                            <visible>String.IsEmpty(ListItem.Property(is.updating)) + !String.IsEmpty(ListItem.Property(left.boundary))</visible>
                                            <posx>91.5</posx>
                                            <posy>{{ vscale(130.5) }}</posy>
                                            <width>61</width>
                                            <height>{{ vscale(100) }}</height>
                                            <texture colordiffuse="40000000">script.plex/indicators/chevron-white-l.png</texture>
                                        </control>
                                        <control type="image">
                                            <visible>!String.IsEmpty(ListItem.Property(is.updating))</visible>
                                            <posx>58</posx>
                                            <posy>{{ vscale(116.5) }}</posy>
                                            <width>128</width>
                                            <height>{{ vscale(128) }}</height>
                                            <texture>script.plex/home/busy.gif</texture>
                                        </control>
                                    </control>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(361) }}</height>
                                        <texture>$INFO[ListItem.Property(thumb.fallback)]</texture>
                                    </control>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(361) }}</height>
                                        <texture background="true">$INFO[ListItem.Thumb]</texture>
                                        <aspectratio>scale</aspectratio>
                                    </control>
                                    <control type="group">
                                        <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                                        <posx>0</posx>
                                        <posy>{{ vscale(351) }}</posy>
                                        <control type="image">
                                            <posx>0</posx>
                                            <posy>0</posy>
                                            <width>244</width>
                                            <height>{{ vscale(10) }}</height>
                                            <texture>script.plex/white-square.png</texture>
                                            <colordiffuse>C0000000</colordiffuse>
                                        </control>
                                        <control type="image">
                                            <posx>0</posx>
                                            <posy>1</posy>
                                            <width>244</width>
                                            <height>{{ vscale(8) }}</height>
                                            <texture>$INFO[ListItem.Property(progress)]</texture>
                                            <colordiffuse>FFCC7B19</colordiffuse>
                                        </control>
                                    </control>
                                    {% include "includes/watched_indicator.xml.tpl" with xoff=244 & uw_size=48 & with_count=True & scale="medium" %}
                                    <control type="label">
                                        <scroll>false</scroll>
                                        <posx>0</posx>
                                        <posy>{{ vscale(369) }}</posy>
                                        <width>244</width>
                                        <height>{{ vscale(38) }}</height>
                                        <font>font10</font>
                                        <align>center</align>
                                        <textcolor>FFFFFFFF</textcolor>
                                        <label>$INFO[ListItem.Label]</label>
                                    </control>
                                </control>
                                <control type="image">
                                    <visible>Control.HasFocus(401)</visible>
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>254</width>
                                    <height>{{ vscale(371) }}</height>
                                    <texture border="10">script.plex/home/selected.png</texture>
                                </control>
                            </control>
                        </control>
                    </focusedlayout>
                </control>
            </control>

            <control type="group" id="503">
                <visible>Integer.IsGreater(Container(403).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
                <defaultcontrol>403</defaultcontrol>
                <width>1920</width>
                <height>{{ vscale(410) }}</height>
                <control type="image">
                    <visible>!String.IsEmpty(Window.Property(divider.403))</visible>
                    <posx>60</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>1800</width>
                    <height>{{ vscale(2) }}</height>
                    <texture>script.plex/white-square.png</texture>
                    <colordiffuse>A0000000</colordiffuse>
                </control>
                <control type="label">
                    <posx>60</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>1000</width>
                    <height>{{ vscale(80) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>[UPPERCASE]$ADDON[script.plexmod 32419][/UPPERCASE]</label>
                </control>
                <control type="list" id="403">
                    <posx>0</posx>
                    <posy>{{ vscale(36) }}</posy>
                    <width>1920</width>
                    <height>{{ vscale(410) }}</height>
                    <onup>401</onup>
                    <ondown>404</ondown>
                    <scrolltime>200</scrolltime>
                    <orientation>horizontal</orientation>
                    <preloaditems>4</preloaditems>
                    <!-- ITEM LAYOUT ########################################## -->
                    <itemlayout width="304">
                        <control type="group">
                           <posx>55</posx>
                            <posy>{{ vscale(61) }}</posy>
                            <control type="group">
                                <posx>5</posx>
                                <posy>5</posy>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>244</width>
                                    <height>{{ vscale(244) }}</height>
                                    <texture diffuse="script.plex/masks/role.png">script.plex/thumb_fallbacks/role.png</texture>
                                </control>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>244</width>
                                    <height>{{ vscale(244) }}</height>
                                    <texture background="true" diffuse="script.plex/masks/role.png">$INFO[ListItem.Thumb]</texture>
                                    <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                                </control>
                                <control type="textbox">
                                    <posx>0</posx>
                                    <posy>{{ vscale(253) }}</posy>
                                    <width>244</width>
                                    <height>{{ vscale(90) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label][CR]$INFO[ListItem.Label2]</label>
                                </control>
                            </control>
                        </control>
                    </itemlayout>

                    <!-- FOCUSED LAYOUT ####################################### -->
                    <focusedlayout width="304">
                        <control type="group">
                            <posx>55</posx>
                            <posy>{{ vscale(61) }}</posy>
                            <control type="group">
                                <animation effect="zoom" start="100" end="110" time="100" center="127,{{ vscale(127) }}" reversible="false">Focus</animation>
                                <animation effect="zoom" start="110" end="100" time="100" center="127,{{ vscale(127) }}" reversible="false">UnFocus</animation>
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="image">
                                    <visible>Control.HasFocus(403)</visible>
                                    <posx>-40</posx>
                                    <posy>{{ vscale(-40) }}</posy>
                                    <width>334</width>
                                    <height>{{ vscale(334) }}</height>
                                    <texture border="42">script.plex/buttons/role-shadow.png</texture>
                                </control>
                                <control type="group">
                                    <posx>5</posx>
                                    <posy>5</posy>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(244) }}</height>
                                        <texture diffuse="script.plex/masks/role.png">script.plex/thumb_fallbacks/role.png</texture>
                                    </control>
                                    <control type="image">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(244) }}</height>
                                        <texture background="true" diffuse="script.plex/masks/role.png">$INFO[ListItem.Thumb]</texture>
                                        <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
                                    </control>
                                    <control type="textbox">
                                        <posx>0</posx>
                                        <posy>{{ vscale(253) }}</posy>
                                        <width>244</width>
                                        <height>{{ vscale(90) }}</height>
                                        <font>font10</font>
                                        <align>center</align>
                                        <textcolor>FFFFFFFF</textcolor>
                                        <label>$INFO[ListItem.Label][CR]$INFO[ListItem.Label2]</label>
                                    </control>
                                </control>
                                <control type="image">
                                    <visible>Control.HasFocus(403)</visible>
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>254</width>
                                    <height>{{ vscale(254) }}</height>
                                    <texture>script.plex/buttons/role-selected.png</texture>
                                </control>
                            </control>
                        </control>
                    </focusedlayout>
                </control>
            </control>
        </control>
    </control>
</control>
{% endblock content %}