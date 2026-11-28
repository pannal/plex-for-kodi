{% extends "default.xml.tpl" %}
{% block headers %}<defaultcontrol>400</defaultcontrol>{% endblock %}
{% block header_anim %}<animation effect="slide" end="0,{{ vscale(-135) }}" time="200" tween="sine" easing="inout" condition="!String.IsEmpty(Window.Property(on.extras)) + !ControlGroup(200).HasFocus(0)">Conditional</animation>{% endblock %}

{% block content %}
<!-- Background -->
<control type="group">
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>1080</height>
        <texture background="true">script.plex/home/background-fallback_black.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>1080</height>
        <fadetime>1000</fadetime>
        <texture background="true">$INFO[Window.Property(background)]</texture>
    </control>
</control>

<!-- Main Content -->
<control type="group" id="50">
    <posx>0</posx>
    <posy>0</posy>
    <!-- Stacking slide animations for discover hub rows -->
    {% for i in range(6) %}
    {% with check_group = i + 501 %}
    <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),{{ i }}) + Control.IsVisible({{ check_group }})" reversible="true">
        <effect type="slide" end="0,{{ vscale(-540) }}" time="200" tween="sine" easing="inout"/>
    </animation>
    {% endwith %}
    {% endfor %}

    <!-- Person Details Section -->
    <control type="group">
        <posx>60</posx>
        <posy>{{ vscale(120) }}</posy>
        <width>1800</width>
        <height>{{ vscale(350) }}</height>

        <!-- Photo (Circular) -->
        <control type="group">
            <posx>0</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(300) }}</height>
                <texture diffuse="script.plex/masks/role.png">script.plex/thumb_fallbacks/role.png</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(300) }}</height>
                <texture background="true" diffuse="script.plex/masks/role.png">$INFO[Window.Property(person.thumb)]</texture>
                <aspectratio scalediffuse="false" aligny="top">scale</aspectratio>
            </control>
        </control>

        <!-- Person Info -->
        <control type="group">
            <posx>340</posx>
            <posy>0</posy>
            <width>1400</width>
            <height>{{ vscale(350) }}</height>

            <!-- Name -->
            <control type="label">
                <posx>0</posx>
                <posy>0</posy>
                <width>1400</width>
                <height>{{ vscale(50) }}</height>
                <font>font_title</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>$INFO[Window.Property(person.name)]</label>
            </control>

            <!-- Role Type (Actor, Director, etc.) -->
            <control type="label">
                <posx>0</posx>
                <posy>{{ vscale(50) }}</posy>
                <width>1400</width>
                <height>{{ vscale(30) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>99FFFFFF</textcolor>
                <label>$INFO[Window.Property(person.type_label)]</label>
            </control>

            <!-- Birth Date and Age -->
            <control type="group">
                <visible>!String.IsEmpty(Window.Property(person.birthDate))</visible>
                <posx>0</posx>
                <posy>{{ vscale(90) }}</posy>

                <control type="label">
                    <visible>!String.IsEmpty(Window.Property(person.age))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>1400</width>
                    <height>{{ vscale(30) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>AAFFFFFF</textcolor>
                    <label>Born $INFO[Window.Property(person.birthDate)] ($INFO[Window.Property(person.age)] years)</label>
                </control>
                <control type="label">
                    <visible>String.IsEmpty(Window.Property(person.age))</visible>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>1400</width>
                    <height>{{ vscale(30) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>AAFFFFFF</textcolor>
                    <label>Born $INFO[Window.Property(person.birthDate)]</label>
                </control>
            </control>

            <!-- Biography -->
            <control type="textbox">
                <posx>0</posx>
                <posy>{{ vscale(130) }}</posy>
                <width>1400</width>
                <height>{{ vscale(160) }}</height>
                <font>font12</font>
                <align>left</align>
                <textcolor>CCFFFFFF</textcolor>
                <scrolltime>200</scrolltime>
                <autoscroll delay="3000" time="3000" repeat="5000"></autoscroll>
                <label>$INFO[Window.Property(person.summary)]</label>
            </control>
        </control>
    </control>

    <!-- Loading Indicator -->
    <control type="group">
        <visible>!String.IsEmpty(Window.Property(loading))</visible>
        <posx>960</posx>
        <posy>{{ vscale(700) }}</posy>
        <control type="image">
            <posx>-32</posx>
            <posy>0</posy>
            <width>64</width>
            <height>{{ vscale(64) }}</height>
            <texture>script.plex/indicators/busy-photo.gif</texture>
        </control>
    </control>

    <!-- Filmography List -->
    <control type="group" id="500">
        <visible>String.IsEmpty(Window.Property(loading))</visible>
        <posx>0</posx>
        <posy>{{ vscale(460) }}</posy>
        <width>1920</width>
        <height>{{ vscale(535) }}</height>

        <control type="label">
            <posx>60</posx>
            <posy>0</posy>
            <width>490</width>
            <height>{{ vscale(87) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[UPPERCASE]$ADDON[script.plexmod 32476][/UPPERCASE]</label>
        </control>
        <control type="button" id="300">
            <posx>560</posx>
            <posy>{{ vscale(18) }}</posy>
            <width>auto</width>
            <height>{{ vscale(50) }}</height>
            <font>font12</font>
            <align>center</align>
            <aligny>center</aligny>
            <focusedcolor>FF000000</focusedcolor>
            <textcolor>FFFFFFFF</textcolor>
            <textoffsetx>15</textoffsetx>
            <texturefocus colordiffuse="FFFFFFFF" border="8">script.plex/white-square-rounded-top-padded.png</texturefocus>
            <texturenofocus colordiffuse="40FFFFFF" border="8">script.plex/white-square-rounded-top-padded.png</texturenofocus>
            <onup>201</onup>
            <ondown condition="Integer.IsGreater(Container(400).NumItems,0)">400</ondown>
            <ondown condition="!Integer.IsGreater(Container(400).NumItems,0)">401</ondown>
            <label>$INFO[Window.Property(filmography.filter)]</label>
        </control>
        <control type="list" id="400">
            <posx>0</posx>
            <posy>{{ vscale(29) }}</posy>
            <width>1920</width>
            <height>{{ vscale(515) }}</height>
            <onup>300</onup>
            <ondown>401</ondown>
            <scrolltime>200</scrolltime>
            <orientation>horizontal</orientation>
            <preloaditems>4</preloaditems>

            <!-- Item Layout -->
            <itemlayout width="287" height="{{ vscale(480) }}">
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
                        <control type="label">
                            <scroll>false</scroll>
                            <posx>0</posx>
                            <posy>{{ vscale(371) }}</posy>
                            <width>244</width>
                            <height>{{ vscale(35) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <textcolor>FFFFFFFF</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <scroll>false</scroll>
                            <posx>0</posx>
                            <posy>{{ vscale(398) }}</posy>
                            <width>244</width>
                            <height>{{ vscale(35) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <textcolor>99FFFFFF</textcolor>
                            <label>$INFO[ListItem.Label2]</label>
                        </control>
                        {% include "includes/watched_indicator.xml.tpl" with xoff=244 & uw_size=48 & with_count=True & scale="medium" %}
                    </control>
                </control>
            </itemlayout>

            <!-- Focused Layout -->
            <focusedlayout width="287" height="{{ vscale(480) }}">
                <control type="group">
                    <posx>55</posx>
                    <posy>{{ vscale(72) }}</posy>
                    <control type="group">
                        <animation effect="zoom" start="100" end="110" time="100" center="127,{{ vscale(180.5) }}" reversible="false">Focus</animation>
                        <animation effect="zoom" start="110" end="100" time="100" center="127,{{ vscale(180.5) }}" reversible="false">UnFocus</animation>
                        <control type="image">
                            <visible>Control.HasFocus(400)</visible>
                            <posx>-40</posx>
                            <posy>{{ vscale(-40) }}</posy>
                            <width>334</width>
                            <height>{{ vscale(451) }}</height>
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
                            <control type="label">
                                <scroll>Control.HasFocus(400)</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(371) }}</posy>
                                <width>244</width>
                                <height>{{ vscale(35) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                            <control type="label">
                                <scroll>false</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(398) }}</posy>
                                <width>244</width>
                                <height>{{ vscale(35) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>99FFFFFF</textcolor>
                                <label>$INFO[ListItem.Label2]</label>
                            </control>
                            {% include "includes/watched_indicator.xml.tpl" with xoff=244 & uw_size=48 & with_count=True & scale="medium" %}
                        </control>
                        <control type="image">
                            <visible>Control.HasFocus(400)</visible>
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

    <!-- Discover Hub Slots (Not in Library) -->
    {% for i in range(6) %}
    {% with list_id = i + 401 & group_id = i + 501 & posy_val = i * 540 + 1000 %}
    <control type="group" id="{{ group_id }}">
        <visible>Integer.IsGreater(Container({{ list_id }}).NumItems,0)</visible>
        <posx>0</posx>
        <posy>{{ vscale(posy_val) }}</posy>
        <width>1920</width>
        <height>{{ vscale(535) }}</height>

        <control type="label">
            <posx>60</posx>
            <posy>0</posy>
            <width>1000</width>
            <height>{{ vscale(87) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[UPPERCASE]$INFO[Window.Property(discover.hub.{{ i }}.label)][/UPPERCASE]</label>
        </control>
        <control type="list" id="{{ list_id }}">
            <posx>0</posx>
            <posy>{{ vscale(29) }}</posy>
            <width>1920</width>
            <height>{{ vscale(515) }}</height>
            {% if loop.is_first %}<onup condition="Integer.IsGreater(Container(400).NumItems,0)">400</onup>
            <onup condition="!Integer.IsGreater(Container(400).NumItems,0)">300</onup>{% else %}<onup>{{ list_id - 1 }}</onup>{% endif %}
            <ondown>{% if loop.is_last %}{{ list_id }}{% else %}{{ list_id + 1 }}{% endif %}</ondown>
            <scrolltime>200</scrolltime>
            <orientation>horizontal</orientation>
            <preloaditems>4</preloaditems>

            <!-- Item Layout -->
            <itemlayout width="287" height="{{ vscale(480) }}">
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
                        <control type="label">
                            <scroll>false</scroll>
                            <posx>0</posx>
                            <posy>{{ vscale(371) }}</posy>
                            <width>244</width>
                            <height>{{ vscale(35) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <textcolor>FFFFFFFF</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <scroll>false</scroll>
                            <posx>0</posx>
                            <posy>{{ vscale(398) }}</posy>
                            <width>244</width>
                            <height>{{ vscale(35) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <textcolor>99FFFFFF</textcolor>
                            <label>$INFO[ListItem.Label2]</label>
                        </control>
                    </control>
                </control>
            </itemlayout>

            <!-- Focused Layout -->
            <focusedlayout width="287" height="{{ vscale(480) }}">
                <control type="group">
                    <posx>55</posx>
                    <posy>{{ vscale(72) }}</posy>
                    <control type="group">
                        <animation effect="zoom" start="100" end="110" time="100" center="127,{{ vscale(180.5) }}" reversible="false">Focus</animation>
                        <animation effect="zoom" start="110" end="100" time="100" center="127,{{ vscale(180.5) }}" reversible="false">UnFocus</animation>
                        <control type="image">
                            <visible>Control.HasFocus({{ list_id }})</visible>
                            <posx>-40</posx>
                            <posy>{{ vscale(-40) }}</posy>
                            <width>334</width>
                            <height>{{ vscale(451) }}</height>
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
                            <control type="label">
                                <scroll>Control.HasFocus({{ list_id }})</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(371) }}</posy>
                                <width>244</width>
                                <height>{{ vscale(35) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>$INFO[ListItem.Label]</label>
                            </control>
                            <control type="label">
                                <scroll>false</scroll>
                                <posx>0</posx>
                                <posy>{{ vscale(398) }}</posy>
                                <width>244</width>
                                <height>{{ vscale(35) }}</height>
                                <font>font10</font>
                                <align>center</align>
                                <textcolor>99FFFFFF</textcolor>
                                <label>$INFO[ListItem.Label2]</label>
                            </control>
                        </control>
                        <control type="image">
                            <visible>Control.HasFocus({{ list_id }})</visible>
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
    {% endwith %}
    {% endfor %}

    <!-- Empty State -->
    <control type="group">
        <visible>String.IsEmpty(Window.Property(loading)) + !Integer.IsGreater(Container(400).NumItems,0)</visible>
        <posx>0</posx>
        <posy>{{ vscale(650) }}</posy>
        <width>1920</width>
        <height>{{ vscale(200) }}</height>

        <control type="label">
            <posx>0</posx>
            <posy>0</posy>
            <width>1920</width>
            <height>{{ vscale(60) }}</height>
            <font>font13</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>99FFFFFF</textcolor>
            <label>$ADDON[script.plexmod 32478]</label>
        </control>
    </control>
</control>
{% endblock content %}
