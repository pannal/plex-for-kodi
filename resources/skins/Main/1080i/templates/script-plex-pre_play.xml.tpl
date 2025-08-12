{% extends "default.xml.tpl" %}
{% block content %}
<control type="group" id="50">
    <animation effect="slide" end="0,{{ vscale(-300) }}" time="200" tween="quadratic" easing="out" condition="!String.IsEmpty(Window.Property(on.extras))">Conditional</animation>

    <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),0) + Control.IsVisible(500)" reversible="true">
        <effect type="slide" end="0,{{ vscale(-500) }}" time="200" tween="quadratic" easing="out"/>
    </animation>

    <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),1) + Control.IsVisible(501)" reversible="true">
        <effect type="slide" end="0,{{ vscale(-500) }}" time="200" tween="quadratic" easing="out"/>
    </animation>

    <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),2) + Control.IsVisible(502)" reversible="true">
        <effect type="slide" end="0,{{ vscale(-500) }}" time="200" tween="quadratic" easing="out"/>
    </animation>

    <posx>0</posx>
    <posy>{{ vscale(155) }}</posy>
    <defaultcontrol>101</defaultcontrol>

    {% block buttons %}
        <control type="grouplist" id="300">
            <animation effect="fade" start="0" end="100" time="200" reversible="true">VisibleChange</animation>
            <visible>!String.IsEmpty(Window.Property(initialized))</visible>
            <defaultcontrol>302</defaultcontrol>
            <posx>428</posx>
            <posy>{{ vscale(410) }}</posy>
            <width>1000</width>
            <height>{{ vscale(145) }}</height>
            <onup>200</onup>
            <ondown>400</ondown>
            <itemgap>{{ theme.pre_play.buttongroup.itemgap }}</itemgap>
            <orientation>horizontal</orientation>
            <scrolltime tween="quadratic" easing="out">200</scrolltime>
            <usecontrolcoords>true</usecontrolcoords>

            {% with attr = theme.pre_play.buttons & template = "includes/themed_button.xml.tpl" %}
                {% include template with name="info" & id=304 %}
                {% include template with name="play" & id=302 & visible="String.IsEmpty(Window.Property(unavailable)) + String.IsEmpty(Window.Property(disable_playback))" %}
                {% include "includes/wl_dynamic_buttons.xml.tpl" %}
                {% include template with name="trailer" & id=303 & visible="!String.IsEmpty(Window.Property(trailer.button))" %}
                {% include "includes/wl_add_remove_buttons.xml.tpl" %}
                {% include template with name="media" & id=307 & visible="!String.IsEmpty(Window.Property(media.multiple))" %}
                {% include template with name="settings" & id=305 & visible="String.IsEmpty(Window.Property(disable_playback))" %}
                {% include template with name="more" & id=306 & visible="String.IsEmpty(Window.Property(disable_playback))" %}
            {% endwith %}

        </control>
    {% endblock %}

    {% block details %}
        <control type="group">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>{{ vscale(600) }}</height>
            <control type="group">
                <visible>!String.IsEmpty(Window.Property(preview.no))</visible>
                <control type="image">
                    <posx>60</posx>
                    <posy>0</posy>
                    <width>347</width>
                    <height>{{ vscale(518) }}</height>
                    <texture background="true">script.plex/thumb_fallbacks/movie.png</texture>
                    <animation effect="fade" start="0" end="100" time="0" delay="500">WindowOpen</animation>
                    <aspectratio>scale</aspectratio>
                </control>
                <control type="image">
                    <posx>60</posx>
                    <posy>0</posy>
                    <width>347</width>
                    <height>{{ vscale(518) }}</height>
                    <texture background="true">$INFO[Window.Property(thumb)]</texture>
                    <aspectratio>scale</aspectratio>
                </control>
                {% include "includes/watched_indicator.xml.tpl" with itemref="Window" & xoff=347+60 & uw_size=48 & scale="medium" %}

            </control>

            <control type="group">
                <visible>!String.IsEmpty(Window.Property(preview.yes))</visible>
                <posx>60</posx>
                <posy>0</posy>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>347</width>
                    <height>{{ vscale(315) }}</height>
                    <texture background="true">script.plex/thumb_fallbacks/show.png</texture>
                    <animation effect="fade" start="0" end="100" time="0" delay="500">WindowOpen</animation>
                    <aspectratio>scale</aspectratio>
                </control>
                <control type="image">
                    <posx>0</posx>
                    <posy>{{ vscale(323) }}</posy>
                    <width>347</width>
                    <height>{{ vscale(195) }}</height>
                    <texture colordiffuse="FF111111">script.plex/white-square.png</texture>
                    <aspectratio>scale</aspectratio>
                </control>

                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>347</width>
                    <height>{{ vscale(315) }}</height>
                    <texture background="true">$INFO[Window.Property(thumb)]</texture>
                    <aspectratio aligny="top">scale</aspectratio>
                </control>
                <control type="image">
                    <posx>0</posx>
                    <posy>{{ vscale(323) }}</posy>
                    <width>347</width>
                    <height>{{ vscale(195) }}</height>
                    <texture background="true">$INFO[Window.Property(preview)]</texture>
                    <aspectratio>scale</aspectratio>
                </control>
            </control>
            <control type="grouplist">
                <posx>466</posx>
                <posy>0</posy>
                <width>1226</width>
                <height>{{ vscale(60) }}</height>
                <align>left</align>
                <itemgap>0</itemgap>
                <scroll>true</scroll>
                <scrollspeed>5</scrollspeed>
                <orientation>horizontal</orientation>
                <usecontrolcoords>true</usecontrolcoords>
                <control type="label">
                    <width>auto</width>
                    <height>{{ vscale(60) }}</height>
                    <font>font13</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[Window.Property(title)]</label>
                </control>
                <control type="button">
                    <visible>!String.IsEmpty(Window.Property(remainingTime))</visible>
                    <posx>10</posx>
                    <posy>6</posy>
                    <width>auto</width>
                    <height>{{ vscale(34) }}</height>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FFE5A00D</focusedcolor>
                    <textcolor>FFE5A00D</textcolor>
                    <textoffsetx>15</textoffsetx>
                    <texturefocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
                    <texturenofocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
                    <label>$INFO[Window.Property(remainingTime)]</label>
                </control>
            </control>
            <control type="grouplist">
                <posx>466</posx>
                <posy>{{ vscale(68) }}</posy>
                <width>1360</width>
                <height>{{ vscale(34) }}</height>
                <align>left</align>
                <itemgap>0</itemgap>
                <orientation>horizontal</orientation>
                <usecontrolcoords>true</usecontrolcoords>
                <control type="label">
                    <width>auto</width>
                    <height>{{ vscale(34) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[Window.Property(duration),, &#8226; ]$INFO[Window.Property(info)]$INFO[Window.Property(date), &#8226; ]$INFO[Window.Property(content.rating), &#8226; ]$INFO[Window.Property(studios), &#8226; ]</label>
                </control>
                <control type="button">
                    <visible>!String.IsEmpty(Window.Property(video.res))</visible>
                    <posx>10</posx>
                    <width>auto</width>
                    <height>{{ vscale(34) }}</height>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FFFFFFFF</focusedcolor>
                    <textcolor>FFFFFFFF</textcolor>
                    <textoffsetx>15</textoffsetx>
                    <texturefocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
                    <texturenofocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
                    <label>$INFO[Window.Property(video.res)]$INFO[Window.Property(video.rendering), &#8226; ]$INFO[Window.Property(video.codec), &#8226; ]$INFO[Window.Property(audio.codec), &#8226; ]$INFO[Window.Property(audio.channels), &#8226; ]</label>
                </control>
                <control type="button">
                    <visible>!String.IsEmpty(Window.Property(unavailable))</visible>
                    <posx>10</posx>
                    <width>auto</width>
                    <height>{{ vscale(34) }}</height>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FFFFFFFF</focusedcolor>
                    <textcolor>FFFFFFFF</textcolor>
                    <textoffsetx>15</textoffsetx>
                    <texturefocus colordiffuse="FFAC3223" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
                    <texturenofocus colordiffuse="FFAC3223" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
                    <label>$ADDON[script.plexmod 32312]</label>
                </control>
            </control>

            <control type="grouplist">
                <visible>!String.IsEmpty(Window.Property(rating)) | !String.IsEmpty(Window.Property(rating2))</visible>
                <posx>1426</posx>
                <posy>4</posy>
                <width>434</width>
                <height>{{ vscale(32) }}</height>
                <align>right</align>
                <itemgap>15</itemgap>
                <orientation>horizontal</orientation>
                <usecontrolcoords>true</usecontrolcoords>
                <control type="image">
                    <visible>!String.IsEmpty(Window.Property(rating))</visible>
                    <posy>2</posy>
                    <width>63</width>
                    <height>{{ vscale(30) }}</height>
                    <texture fallback="script.plex/ratings/other/image.rating.png">$INFO[Window.Property(rating.image)]</texture>
                    <aspectratio align="right">keep</aspectratio>
                </control>
                <control type="label">
                    <visible>!String.IsEmpty(Window.Property(rating))</visible>
                    <width>auto</width>
                    <height>{{ vscale(30) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[Window.Property(rating)]</label>
                </control>
                <control type="image">
                    <visible>!String.IsEmpty(Window.Property(rating2))</visible>
                    <posy>2</posy>
                    <width>40</width>
                    <height>{{ vscale(30) }}</height>
                    <texture fallback="script.plex/ratings/other/image.rating.png">$INFO[Window.Property(rating2.image)]</texture>
                    <aspectratio align="right">keep</aspectratio>
                </control>
                <control type="label">
                    <visible>!String.IsEmpty(Window.Property(rating2))</visible>
                    <width>auto</width>
                    <height>{{ vscale(30) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[Window.Property(rating2)]</label>
                </control>
                <control type="image">
                    <visible>!String.IsEmpty(Window.Property(rating.stars))</visible>
                    <posy>6</posy>
                    <width>134</width>
                    <height>{{ vscale(22) }}</height>
                    <texture>script.plex/stars/$INFO[Window.Property(rating.stars)].png</texture>
                </control>
            </control>
            {% block cast_detail_and_streams %}
                <control type="label">
                    <visible>!String.IsEmpty(Window.Property(directors)) | !String.IsEmpty(Window.Property(writers))</visible>
                    <posx>466</posx>
                    <posy>{{ vscale(130) }}</posy>
                    <width>1360</width>
                    <height>{{ vscale(30) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>99FFFFFF</textcolor>
                    <label>$INFO[Window.Property(directors)]$INFO[Window.Property(writers)]</label>
                </control>
                <control type="label">
                    <visible>!String.IsEmpty(Window.Property(cast))</visible>
                    <posx>466</posx>
                    <posy>{{ vscale(165) }}</posy>
                    <width>1360</width>
                    <height>{{ vscale(30) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>99FFFFFF</textcolor>
                    <label>$INFO[Window.Property(cast)]</label>
                </control>
                {% block streams %}
                    <control type="grouplist">
                        <posx>466</posx>
                        <posy>{{ vscale(223) }}</posy>
                        <width>1360</width>
                        <height>{{ vscale(34) }}</height>
                        <align>left</align>
                        <itemgap>15</itemgap>
                        <orientation>horizontal</orientation>
                        <usecontrolcoords>true</usecontrolcoords>
                        <control type="button">
                            <visible>!String.IsEmpty(Window.Property(audio))</visible>
                            <width>auto</width>
                            <height>{{ vscale(34) }}</height>
                            <font>font12</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <focusedcolor>FFFFFFFF</focusedcolor>
                            <textcolor>FFFFFFFF</textcolor>
                            <textoffsetx>15</textoffsetx>
                            <texturefocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
                            <texturenofocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
                            <label>[UPPERCASE]$ADDON[script.plexmod 32048][/UPPERCASE]</label>
                        </control>
                        <control type="label">
                            <width>auto</width>
                            <height>{{ vscale(34) }}</height>
                            <font>font12</font>
                            <align>left</align>
                            <aligny>center</aligny>
                            <textcolor>FFFFFFFF</textcolor>
                            <label>$INFO[Window.Property(audio)]</label>
                        </control>
                        <control type="button">
                            <visible>!String.IsEmpty(Window.Property(subtitles))</visible>
                            <left>30</left>
                            <width>auto</width>
                            <height>{{ vscale(34) }}</height>
                            <font>font12</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <focusedcolor>FFFFFFFF</focusedcolor>
                            <textcolor>FFFFFFFF</textcolor>
                            <textoffsetx>15</textoffsetx>
                            <texturefocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
                            <texturenofocus colordiffuse="40000000" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
                            <label>[UPPERCASE]$ADDON[script.plexmod 32396][/UPPERCASE]</label>
                        </control>
                        <control type="label">
                            <visible>!String.IsEmpty(Window.Property(subtitles))</visible>
                            <width>auto</width>
                            <height>{{ vscale(34) }}</height>
                            <font>font12</font>
                            <align>left</align>
                            <aligny>center</aligny>
                            <textcolor>FFFFFFFF</textcolor>
                            <label>$INFO[Window.Property(subtitles)]</label>
                        </control>
                    </control>
                {% endblock %}
            {% endblock %}
            {% block summary %}
                <control type="textbox">
                    <posx>466</posx>
                    <posy>{{ vscale(290) }}</posy>
                    <width>1360</width>
                    <height>{{ vscale(102) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <textcolor>FFFFFFFF</textcolor>
                    <scrolltime>200</scrolltime>
                    <autoscroll delay="2000" time="2000" repeat="10000">!Control.HasFocus(13)</autoscroll>
                    <label>$INFO[Window.Property(summary)]</label>
                </control>
            {% endblock %}
            <control type="image" id="250">
                <animation effect="zoom" start="0,100" end="100,100" time="1000" center="-1,561" reversible="false" tween="circle" easing="out">WindowOpen</animation>
                <posx>-1</posx>
                <posy>{{ vscale(557) }}</posy>
                <width>1</width>
                <height>{{ vscale(8) }}</height>
                <texture>script.plex/white-square.png</texture>
                <colordiffuse>FFCC7B19</colordiffuse>
            </control>
            <control type="image">
                <visible>!Control.IsVisible(500)</visible>
                <posx>0</posx>
                <posy>{{ vscale(565) }}</posy>
                <width>1920</width>
                <height>{{ vscale(2) }}</height>
                <texture>script.plex/white-square.png</texture>
                <colordiffuse>A0000000</colordiffuse>
            </control>
        </control>
    {% endblock %}

    <control type="grouplist" id="60">
        <posx>0</posx>
        <posy>{{ vscale(540) }}</posy>
        <width>1920</width>
        <height>{{ vscale(1800) }}</height>

        <onup>300</onup>
        <itemgap>0</itemgap>

        <!-- ROLES -->
        <control type="group" id="500">
            <visible>Integer.IsGreater(Container(400).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
            <defaultcontrol>400</defaultcontrol>
            <width>1920</width>
            <height>{{ vscale(446) }}</height>
            <control type="list" id="400">
                <posx>0</posx>
                <posy>0</posy>
                <width>1920</width>
                <height>{{ vscale(410) }}</height>
                <onup>300</onup>
                <ondown>401</ondown>
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
                            <control type="group">
                                <posx>0</posx>
                                <posy>{{ vscale(253) }}</posy>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>244</width>
                                    <height>{{ vscale(60) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>AAFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                </control>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>0</posx>
                                    <posy>{{ vscale(30) }}</posy>
                                    <width>244</width>
                                    <height>{{ vscale(60) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>AAFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                </control>
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
                                <control type="group">
                                    <posx>0</posx>
                                    <posy>{{ vscale(253) }}</posy>
                                    <control type="label">
                                        <scroll>Control.HasFocus(400)</scroll>
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>244</width>
                                        <height>{{ vscale(60) }}</height>
                                        <font>font10</font>
                                        <align>center</align>
                                        <textcolor>AAFFFFFF</textcolor>
                                        <label>$INFO[ListItem.Label]</label>
                                    </control>
                                    <control type="label">
                                        <scroll>Control.HasFocus(400)</scroll>
                                        <posx>0</posx>
                                        <posy>{{ vscale(30) }}</posy>
                                        <width>244</width>
                                        <height>{{ vscale(60) }}</height>
                                        <font>font10</font>
                                        <align>center</align>
                                        <textcolor>AAFFFFFF</textcolor>
                                        <label>$INFO[ListItem.Label2]</label>
                                    </control>
                                </control>
                            </control>
                            <control type="image">
                                <visible>Control.HasFocus(400)</visible>
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
        <!-- /ROLES -->

        <!-- REVIEWS -->
        <control type="group" id="501">
            <visible>Integer.IsGreater(Container(401).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
            <defaultcontrol>401</defaultcontrol>
            <width>1920</width>
            <height>{{ vscale(446) }}</height>
            <control type="label">
                <posx>60</posx>
                <posy>{{ vscale(20) }}</posy>
                <width>1000</width>
                <height>{{ vscale(80) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>[UPPERCASE]$ADDON[script.plexmod 32953][/UPPERCASE]</label>
            </control>
            <control type="list" id="401">
                <posx>0</posx>
                <posy>{{ vscale(36) }}</posy>
                <width>1920</width>
                <height>{{ vscale(410) }}</height>
                <onup>400</onup>
                <ondown>402</ondown>
                <scrolltime>200</scrolltime>
                <orientation>horizontal</orientation>
                <preloaditems>4</preloaditems>
                <!-- ITEM LAYOUT ########################################## -->
                <itemlayout width="540">
                    <control type="group">
                        <posx>55</posx>
                        <posy>{{ vscale(61) }}</posy>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>520</width>
                            <height>{{ vscale(310) }}</height>
                            <texture>script.plex/white-square.png</texture>
                            <colordiffuse>60000000</colordiffuse>
                        </control>
                        <control type="group">
                            <posx>20</posx>
                            <posy>{{ vscale(20) }}</posy>
                            <control type="group">
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="image">
                                    <posx>10</posx>
                                    <posy>{{ vscale(-5) }}</posy>
                                    <width>70</width>
                                    <height>{{ vscale(70) }}</height>
                                    <texture>script.plex/reviews/$INFO[ListItem.Thumb].png</texture>
                                </control>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>100</posx>
                                    <posy>0</posy>
                                    <width>400</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <textcolor>DDFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                </control>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>100</posx>
                                    <posy>{{ vscale(30) }}</posy>
                                    <width>400</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <textcolor>66FFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                </control>
                            </control>
                            <control type="textbox">
                                <posx>0</posx>
                                <posy>{{ vscale(80) }}</posy>
                                <width>480</width>
                                <height>{{ vscale(190) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <textcolor>AAFFFFFF</textcolor>
                                <label>$INFO[ListItem.Property(text)]</label>
                            </control>
                        </control>
                    </control>
                </itemlayout>

                <!-- FOCUSED LAYOUT ####################################### -->
                <focusedlayout width="540">
                    <control type="group">
                        <posx>55</posx>
                        <posy>{{ vscale(61) }}</posy>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>520</width>
                            <height>{{ vscale(310) }}</height>
                            <texture>script.plex/white-square.png</texture>
                            <colordiffuse>80000000</colordiffuse>
                        </control>
                        <control type="group">
                            <posx>20</posx>
                            <posy>{{ vscale(20) }}</posy>
                            <control type="group">
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="image">
                                    <posx>10</posx>
                                    <posy>{{ vscale(-5) }}</posy>
                                    <width>70</width>
                                    <height>{{ vscale(70) }}</height>
                                    <texture>script.plex/reviews/$INFO[ListItem.Thumb].png</texture>
                                </control>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>100</posx>
                                    <posy>0</posy>
                                    <width>400</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <textcolor>DDFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                </control>
                                <control type="label">
                                    <scroll>false</scroll>
                                    <posx>100</posx>
                                    <posy>{{ vscale(30) }}</posy>
                                    <width>400</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <textcolor>66FFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                </control>
                            </control>
                            <control type="textbox">
                                <posx>0</posx>
                                <posy>{{ vscale(80) }}</posy>
                                <width>480</width>
                                <height>{{ vscale(190) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <textcolor>DDFFFFFF</textcolor>
                                <label>$INFO[ListItem.Property(text)]</label>
                                <autoscroll delay="6000" time="3000" repeat="12000">Control.HasFocus(401)</autoscroll>
                            </control>
                        </control>
                        <control type="image">
                            <visible>Control.HasFocus(401)</visible>
                            <posx>-5</posx>
                            <posy>{{ vscale(-5) }}</posy>
                            <width>530</width>
                            <height>{{ vscale(320) }}</height>
                            <texture border="10">script.plex/home/selected.png</texture>
                        </control>
                    </control>
                </focusedlayout>
            </control>
        </control>
        <!-- /REVIEWS -->

        <!-- EXTRAS -->
        <control type="group" id="502">
            <visible>Integer.IsGreater(Container(402).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
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
                <label>[UPPERCASE]$ADDON[script.plexmod 32305][/UPPERCASE]</label>
            </control>
            <control type="list" id="402">
                <posx>0</posx>
                <posy>{{ vscale(18) }}</posy>
                <width>1920</width>
                <height>{{ vscale(430) }}</height>
                <onup>401</onup>
                <ondown>403</ondown>
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
                            <control type="textbox">
                                <posx>0</posx>
                                <posy>{{ vscale(180) }}</posy>
                                <width>299</width>
                                <height>{{ vscale(60) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>$INFO[ListItem.Label]</label>
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
                                <visible>Control.HasFocus(402)</visible>
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
                                <control type="textbox">
                                    <posx>0</posx>
                                    <posy>{{ vscale(180) }}</posy>
                                    <width>299</width>
                                    <height>{{ vscale(60) }}</height>
                                    <font>font10</font>
                                    <align>center</align>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label]</label>
                                </control>
                            </control>
                            <control type="image">
                                <visible>Control.HasFocus(402)</visible>
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
        <!-- /EXTRAS -->

        <!-- RELATED -->
        <control type="group" id="503">
            <visible>Integer.IsGreater(Container(403).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
            <defaultcontrol>403</defaultcontrol>
            <width>1920</width>
            <height>{{ vscale(520) }}</height>
            <control type="image">
                <visible>!String.IsEmpty(Window.Property(divider.403))</visible>
                <posx>60</posx>
                <posy>0</posy>
                <width>1800</width>
                <height>{{ vscale(2) }}</height>
                <texture>script.plex/white-square.png</texture>
                <colordiffuse>A0000000</colordiffuse>
            </control>
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
            <control type="list" id="403">
                <posx>0</posx>
                <posy>{{ vscale(16) }}</posy>
                <width>1920</width>
                <height>{{ vscale(520) }}</height>
                <onup>402</onup>
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
                                <visible>Control.HasFocus(403)</visible>
                                <posx>-40</posx>
                                <posy>{{ vscale(-40) }}</posy>
                                <width>324</width>
                                <height>{{ vscale(441) }}</height>
                                <texture border="42">script.plex/drop-shadow.png</texture>
                            </control>
                            <control type="group">
                                <posx>5</posx>
                                <posy>5</posy>
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
                                    <scroll>Control.HasFocus(403)</scroll>
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
                                <visible>Control.HasFocus(403)</visible>
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>254</width>
                                <height>{{ vscale(371) }}</height>
                                <texture border="10">script.plex/home/selected.png</texture>
                            </control>
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
                        </control>
                    </control>
                </focusedlayout>
            </control>
        </control>
        <!-- /RELATED -->
    </control>
</control>
{% endblock content %}