from dataclasses import dataclass

from desk_robot.context import ConversationContext
from desk_robot.information import (
    InformationError,
    NewsProvider,
    OpenMeteoWeatherProvider,
    RssNewsProvider,
    WeatherProvider,
)
from desk_robot.personality import Personality


@dataclass
class RobotState:
    name: str = "Debo"
    mood: str = "curious"
    turns: int = 0


class DeskRobot:
    def __init__(
        self,
        name: str = "Debo",
        context_limit: int = 5,
        weather_provider: WeatherProvider | None = None,
        news_provider: NewsProvider | None = None,
    ) -> None:
        self.state = RobotState(name=name)
        self.personality = Personality()
        self.context = ConversationContext(max_turns=context_limit)
        self.weather_provider = (
            weather_provider
            if weather_provider is not None
            else OpenMeteoWeatherProvider()
        )
        self.news_provider = (
            news_provider if news_provider is not None else RssNewsProvider()
        )
        self.last_weather_report = None
        self.last_news_report = None
        self.last_intent = "unknown"
        self.news_cache = None
        self.last_news_index = 0
        self.last_story_text: str | None = None

    def respond(self, message: str) -> str:
        original_message = message.strip()
        normalised = original_message.lower()

        if not original_message:
            return "I'm listening... say something!"

        self.state.turns += 1
        previous_message = self.context.last_user_message
        self.last_weather_report = None
        self.last_news_report = None
        self.last_intent = "unknown"
        self.last_story_text = None

        intent = "unknown"

        if normalised in {"hello", "hi", "hey", "hello robot"}:
            intent = "greeting"
        elif "your name" in normalised or "what is your name" in normalised:
            intent = "name"
        elif "how are you" in normalised:
            intent = "mood"
        elif "thank" in normalised:
            intent = "thanks"
        elif normalised in {"bye", "goodbye", "exit", "quit"}:
            intent = "farewell"
        elif (
            "what did i just say" in normalised
            or "what did i say" in normalised
            or "what was my last message" in normalised
        ):
            intent = "recall"
        elif "help" in normalised:
            intent = "help"
        elif self._is_weather_request(normalised):
            intent = "weather"
        elif any(phrase in normalised for phrase in ("read the full story", "read full story", "read me the story", "read this story", "full story", "read the article", "read article")):
            intent = "full_story"
        elif any(phrase in normalised for phrase in ("next story", "another story", "next headline")):
            intent = "next_news"
        elif self._is_news_request(normalised):
            intent = "news"

        self.last_intent = intent

        if intent == "weather":
            location = self._weather_location(original_message)

            if not location:
                response = (
                    "Which location would you like the weather for? "
                    "For example, weather in London."
                )
            else:
                try:
                    report = self.weather_provider.fetch_current(location)
                    self.last_weather_report = report
                    response = (
                        f"Here's the current weather for {report.location}: "
                        f"{report.condition}, {report.temperature_c:.1f}°C. "
                        f"Source: {report.provider}."
                    )
                    if report.observed_at is not None:
                        response += (
                            " Conditions observed at "
                            f"{report.observed_at.strftime('%H:%M UTC')}."
                        )
                except InformationError as error:
                    response = str(error)

        elif intent == "news":
            try:
                report = self.news_provider.fetch_latest(limit=5)
                self.last_news_report = report
                self.news_cache = report
                self.last_news_index = 0
                if report.articles:
                    response = f"I've found {len(report.articles)} headlines. Want the next story?"
                else:
                    response = "The news feed returned no headlines."
            except InformationError as error:
                response = str(error)

        elif intent == "full_story":
            if not self.news_cache or not self.news_cache.articles:
                response = "Ask me for the news first, then say read the full story."
            else:
                index = min(max(0, self.last_news_index), len(self.news_cache.articles) - 1)
                article = self.news_cache.articles[index]
                self.last_news_report = self.news_cache
                fetch_story = getattr(self.news_provider, "fetch_story", None)
                if fetch_story is None:
                    response = "This news source doesn't support full-story reading yet."
                else:
                    try:
                        self.last_story_text = f"{article.title}. {fetch_story(article)}"
                        response = f"All right. I'll read the full story: {article.title}."
                    except InformationError as error:
                        response = str(error)
                        self.last_story_text = None

        elif intent == "next_news":
            if self.news_cache and self.news_cache.articles:
                self.last_news_report = self.news_cache
                self.last_news_index = (self.last_news_index + 1) % len(self.news_cache.articles)
                article = self.news_cache.articles[self.last_news_index]
                response = f"Story {self.last_news_index + 1} of {len(self.news_cache.articles)}: {article.title}"
            else:
                response = "Ask me for the news first, and I'll find a story for you."

        else:
            response = self.personality.respond(
                intent=intent,
                name=self.state.name,
                mood=self.state.mood,
                previous_message=previous_message,
            )

        self.context.add_turn(original_message, response)
        return response

    @staticmethod
    def _is_weather_request(message: str) -> bool:
        return any(word in message for word in ("weather", "temperature", "forecast"))

    @staticmethod
    def _is_news_request(message: str) -> bool:
        return any(
            phrase in message
            for phrase in (
                "news",
                "headlines",
                "latest stories",
                "what's happening",
                "what is happening",
            )
        )

    @staticmethod
    def _weather_location(message: str) -> str | None:
        normalised = message.lower()
        markers = (
            "weather in ",
            "weather for ",
            "temperature in ",
            "temperature for ",
            "forecast in ",
            "forecast for ",
        )

        for marker in markers:
            position = normalised.find(marker)
            if position >= 0:
                location = message[position + len(marker) :].strip(" .?!")
                return location or None

        return None
